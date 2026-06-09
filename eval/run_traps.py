"""Trap evaluation: the confidently-wrong reduction from the trust layer.

BIRD questions are well-specified, so the clarification arm never fires there. This
eval uses questions that should NOT be confidently answered (ambiguous, unanswerable,
prompt-injection) over the Olist demo DB, and measures how often each pipeline answers
anyway:

  - baseline (no trust): generates and executes -> "answered" or "failed"
  - trust: clarifies, fails (validator/execution), or "answered"

A confident answer to a should-decline question is the harm. The reduction in
"answered" rate on traps, against the over-decline rate on clear controls, is the
signature number. Threshold-free: clarification is the primary defense, so the
headline is whether the layer answered at all.

    uv run python eval/run_traps.py --model claude-sonnet-4-6 --k 3
    uv run python eval/run_traps.py --dry-run        # no API
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sqlite3
from pathlib import Path
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.llm import AnthropicClient, LLMClient, build_client
from backend.app.pipeline.ambiguity import detect_ambiguity
from backend.app.pipeline.confidence import (
    compute_confidence,
    load_calibration_map,
    self_consistency,
)
from backend.app.pipeline.execute import ValidationError, execute_query
from backend.app.pipeline.generate import generate_sql, generate_with_self_correction
from backend.app.pipeline.schema import build_schema_card
from backend.app.semantic_layer import render_semantic_layer
from eval.metrics import (
    ClarificationScores,
    LabeledResult,
    TrapRecord,
    TrapScores,
    clarification_precision_recall,
    trap_scores,
)
from eval.run_bird import PRICES, DryRunClient

LABELED_PATH = Path(__file__).parent / "labeled_ambiguity.json"
OUT_DIR = Path(__file__).parent / "out"
RESULTS_PATH = OUT_DIR / "trap_results.json"
EVAL_ROW_CAP = 10000


def _baseline_outcome(
    prompt: str, *, client: LLMClient, model: str, schema_context: str, settings: Settings
) -> str:
    try:
        gen = generate_sql(
            prompt,
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context="",
            temperature=0.0,
        )
        execution = execute_query(
            gen.sql,
            settings.demo_db_path,
            default_limit=EVAL_ROW_CAP,
            timeout_seconds=settings.sql_timeout_seconds,
        )
        return "failed" if execution.timed_out else "answered"
    except (ValidationError, sqlite3.Error):
        return "failed"


def evaluate_trap(
    item: dict[str, Any], *, client: LLMClient, model: str, settings: Settings
) -> TrapRecord:
    """Run both pipelines on one trap/clear question over the demo DB."""
    prompt = str(item["question"])
    schema_context = build_schema_card(settings.demo_db_path)
    semantic_context = render_semantic_layer()
    eval_settings = dataclasses.replace(settings, sql_default_limit=EVAL_ROW_CAP)

    # --- trust ---
    report = detect_ambiguity(
        prompt,
        client=client,
        model=model,
        schema_context=schema_context,
        semantic_context=semantic_context,
    )
    trust_confidence: float | None = None
    if report.needs_clarification:
        trust_outcome = "clarified"
    else:
        result = generate_with_self_correction(
            prompt,
            client=client,
            model=model,
            db_path=settings.demo_db_path,
            schema_context=schema_context,
            semantic_context=semantic_context,
            settings=eval_settings,
        )
        execution = result.execution
        if execution is None or execution.timed_out:
            trust_outcome = "failed"
        else:
            trust_outcome = "answered"
            agree, k = self_consistency(
                prompt,
                client=client,
                model=model,
                db_path=settings.demo_db_path,
                schema_context=schema_context,
                semantic_context=semantic_context,
                settings=eval_settings,
                primary_execution=execution,
            )
            conf = compute_confidence(
                agreement=agree,
                samples=k,
                self_correction_fired=result.self_correction_fired,
                retrieval_score=1.0,
                calibration=load_calibration_map(settings.calibration_path),
            )
            trust_confidence = conf.score

    baseline_outcome = _baseline_outcome(
        prompt, client=client, model=model, schema_context=schema_context, settings=settings
    )

    return TrapRecord(
        id=str(item["id"]),
        category=str(item["category"]),
        should_decline=bool(item["ambiguous"]),
        trust_outcome=trust_outcome,
        trust_confidence=trust_confidence,
        baseline_outcome=baseline_outcome,
    )


def _clarification_over_genuine_ambiguity(
    items: list[dict[str, Any]], records_by_id: dict[str, TrapRecord]
) -> ClarificationScores:
    """Clarification P/R over genuinely-ambiguous items (excludes prompt-injection, which the
    SELECT-only validator handles, not the ambiguity gate) plus clear controls."""
    labeled: list[LabeledResult] = []
    for item in items:
        if item["category"] == "prompt_injection":
            continue
        rec = records_by_id[str(item["id"])]
        labeled.append(
            LabeledResult(
                ambiguous=bool(item["ambiguous"]), flagged=rec["trust_outcome"] == "clarified"
            )
        )
    return clarification_precision_recall(labeled)


def _mean_conf(records: list[TrapRecord], should_decline: bool) -> float | None:
    vals = [
        r["trust_confidence"]
        for r in records
        if r["should_decline"] == should_decline
        and r["trust_outcome"] == "answered"
        and r["trust_confidence"] is not None
    ]
    return round(sum(vals) / len(vals), 4) if vals else None


def _estimated_cost(client: LLMClient, model: str) -> float:
    if not isinstance(client, AnthropicClient):
        return 0.0
    in_price, out_price = PRICES.get(model, (0.0, 0.0))
    return client.input_tokens / 1e6 * in_price + client.output_tokens / 1e6 * out_price


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the trap eval (confidently-wrong reduction).")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    labeled = json.loads(LABELED_PATH.read_text(encoding="utf-8"))
    items: list[dict[str, Any]] = labeled["questions"]
    settings = dataclasses.replace(
        get_settings(), self_consistency_samples=args.k, generation_model=args.model
    )
    client: LLMClient = DryRunClient() if args.dry_run else build_client()

    records: list[TrapRecord] = [
        evaluate_trap(item, client=client, model=args.model, settings=settings) for item in items
    ]
    by_id = {r["id"]: r for r in records}

    scores: TrapScores = trap_scores(records)
    clar = _clarification_over_genuine_ambiguity(items, by_id)
    cost = _estimated_cost(client, args.model)

    report = {
        "metadata": {
            "model": args.model,
            "k": args.k,
            "n_items": len(records),
            "estimated_cost_usd": round(cost, 4),
        },
        "confidently_answered_on_traps": dataclasses.asdict(scores),
        "mean_confidence_when_answered": {
            "traps": _mean_conf(records, should_decline=True),
            "clear": _mean_conf(records, should_decline=False),
        },
        "clarification": dataclasses.asdict(clar),
        "records": records,
    }
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Wrote {RESULTS_PATH} ({len(records)} items, ${cost:.2f}).")
    print(
        f"  traps: baseline answered {scores.baseline_confidently_answered:.2f} -> "
        f"trust answered {scores.trust_confidently_answered:.2f} "
        f"(abs reduction {scores.absolute_reduction:.2f})"
    )
    print(f"  over-decline on clear controls: {scores.over_decline_rate:.2f}")
    print(f"  clarification P/R (genuine ambiguity): {clar.precision:.2f} / {clar.recall:.2f}")


if __name__ == "__main__":
    main()
