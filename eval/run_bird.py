"""BIRD dev evaluation runner (offline batch).

Runs the pinned subset through both the trust pipeline and a no-trust baseline,
compares each result set to gold, and writes committed metrics + a fitted
calibration map. Processes one database at a time to stay within the memory
budget; resumable so an interrupted paid run never re-charges completed work.

    uv run python eval/run_bird.py --model claude-haiku-4-5 --k 3 --max-cost 4
    uv run python eval/run_bird.py --dry-run --limit 3      # plumbing, no API

The displayed primary answer is temperature 0 (reproducible); the K-1 confidence
samples use nonzero temperature, so confidence can vary slightly between runs.
The committed eval_results.json is the canonical record.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import psutil

from backend.app.config import Settings, get_settings
from backend.app.llm import AnthropicClient, LLMClient, build_client
from backend.app.pipeline.ambiguity import AmbiguityReport, detect_ambiguity
from backend.app.pipeline.confidence import (
    canonicalize_rows,
    compute_confidence,
    load_calibration_map,
    self_consistency,
)
from backend.app.pipeline.execute import ValidationError, execute_query
from backend.app.pipeline.execute import _open_readonly as open_readonly
from backend.app.pipeline.generate import SqlGeneration, generate_sql, generate_with_self_correction
from backend.app.pipeline.schema import build_schema_card
from backend.app.semantic_layer import render_semantic_layer
from eval.ablation import compute_ablation
from eval.calibrate import build_map, isotonic_fit, write_calibration_map
from eval.metrics import (
    CONFIDENT_THRESHOLD,
    EvalRecord,
    LabeledResult,
    answered_accuracy,
    baseline_confidently_wrong_rate,
    brier_score,
    clarification_precision_recall,
    clarification_rate,
    confidently_wrong_rate,
    execution_accuracy,
    expected_calibration_error,
    reliability_bins,
    semantic_error_rate,
)
from eval.prep_bird import bird_db_path

SUBSET_PATH = Path(__file__).parent / "bird_subset.json"
LABELED_PATH = Path(__file__).parent / "labeled_ambiguity.json"
OUT_DIR = Path(__file__).parent / "out"
PARTIAL_PATH = OUT_DIR / "results.partial.jsonl"
RESULTS_PATH = OUT_DIR / "eval_results.json"

# Large enough that gold and predicted sets are compared in full, not truncated.
EVAL_ROW_CAP = 10000
# Held-out fraction for calibration evaluation.
TEST_FRACTION = 0.4

# $ per million tokens (input, output).
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (5.0, 25.0),
}


class DryRunClient:
    """Stub LLMClient for --dry-run: no API calls, fixed structured outputs."""

    def generate_structured(
        self, *, model: str, system: str, user: str, output_format: type[Any], temperature: float
    ) -> Any:
        if output_format is AmbiguityReport:
            return AmbiguityReport(needs_clarification=False)
        return SqlGeneration(sql="SELECT 1 AS x", explanation="dry-run stub")


def _execute_gold(
    sql: str, db_path: str, cap: int
) -> tuple[list[str], list[tuple[Any, ...]]] | None:
    """Execute gold SQL raw read-only (no validator/re-emit). None on any error."""
    conn = open_readonly(db_path)
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description or []]
        rows: list[tuple[Any, ...]] = cursor.fetchmany(cap)
        return columns, rows
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _classify_error(error: str | None) -> str:
    if error is None:
        return "none"
    low = error.lower()
    if "validator" in low:
        return "validation"
    if "sqlite" in low:
        return "sqlite"
    return "no_answer"


def evaluate_question(
    question: dict[str, Any],
    *,
    client: LLMClient,
    model: str,
    settings: Settings,
) -> EvalRecord:
    """Run one BIRD question through both pipelines and score against gold."""
    db_id = str(question["db_id"])
    db_path = str(bird_db_path(db_id))
    gold_sql = str(question["SQL"])
    evidence = str(question.get("evidence") or "")
    prompt = str(question["question"])
    if evidence:
        prompt = f"{prompt}\nHint: {evidence}"

    schema_context = build_schema_card(db_path)
    semantic_context = ""  # Olist business terms do not apply to BIRD schemas.
    eval_settings = dataclasses.replace(settings, sql_default_limit=EVAL_ROW_CAP)

    gold = _execute_gold(gold_sql, db_path, EVAL_ROW_CAP)
    gold_canon = canonicalize_rows(gold[0], gold[1]) if gold is not None else None

    started = time.monotonic()

    # --- with trust ---
    report = detect_ambiguity(
        prompt,
        client=client,
        model=model,
        schema_context=schema_context,
        semantic_context=semantic_context,
    )
    clarified = report.needs_clarification
    executed_ok = False
    correct = False
    error_class = "no_answer"
    predicted_sql = ""
    confidence_raw: float | None = None
    confidence_score: float | None = None
    agreement: float | None = None
    self_correction_fired = False

    if not clarified:
        result = generate_with_self_correction(
            prompt,
            client=client,
            model=model,
            db_path=db_path,
            schema_context=schema_context,
            semantic_context=semantic_context,
            settings=eval_settings,
        )
        predicted_sql = result.sql
        self_correction_fired = result.self_correction_fired
        execution = result.execution
        if execution is not None and not execution.timed_out:
            executed_ok = True
            error_class = "none"
            pred_canon = canonicalize_rows(execution.columns, execution.rows)
            correct = gold_canon is not None and pred_canon == gold_canon
            agree, k = self_consistency(
                prompt,
                client=client,
                model=model,
                db_path=db_path,
                schema_context=schema_context,
                semantic_context=semantic_context,
                settings=eval_settings,
                primary_execution=execution,
            )
            conf = compute_confidence(
                agreement=agree,
                samples=k,
                self_correction_fired=self_correction_fired,
                retrieval_score=1.0,
                calibration=load_calibration_map(settings.calibration_path),
            )
            agreement = agree
            confidence_raw = conf.raw
            confidence_score = conf.score
        elif execution is not None and execution.timed_out:
            error_class = "timeout"
        else:
            error_class = _classify_error(result.error)

    # --- baseline (no trust): single generation, execute, score ---
    baseline_executed_ok = False
    baseline_correct = False
    try:
        gen = generate_sql(
            prompt,
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context=semantic_context,
            temperature=0.0,
        )
        baseline_exec = execute_query(
            gen.sql,
            db_path,
            default_limit=EVAL_ROW_CAP,
            timeout_seconds=settings.sql_timeout_seconds,
        )
        if not baseline_exec.timed_out:
            baseline_executed_ok = True
            baseline_canon = canonicalize_rows(baseline_exec.columns, baseline_exec.rows)
            baseline_correct = gold_canon is not None and baseline_canon == gold_canon
    except (ValidationError, sqlite3.Error):
        pass

    latency_ms = (time.monotonic() - started) * 1000.0

    return EvalRecord(
        question_id=int(question["question_id"]),
        db_id=db_id,
        difficulty=str(question["difficulty"]),
        clarified=clarified,
        executed_ok=executed_ok,
        correct=correct,
        error_class=error_class,
        confidence_raw=confidence_raw,
        confidence_score=confidence_score,
        agreement=agreement,
        self_correction_fired=self_correction_fired,
        predicted_sql=predicted_sql,
        baseline_executed_ok=baseline_executed_ok,
        baseline_correct=baseline_correct,
        latency_ms=latency_ms,
    )


def _estimated_cost(client: LLMClient, model: str) -> float:
    if not isinstance(client, AnthropicClient):
        return 0.0
    in_price, out_price = PRICES.get(model, (0.0, 0.0))
    return client.input_tokens / 1e6 * in_price + client.output_tokens / 1e6 * out_price


def run_subset(
    questions: list[dict[str, Any]],
    *,
    client: LLMClient,
    model: str,
    settings: Settings,
    max_cost: float | None = None,
    on_record: Any = None,
) -> list[EvalRecord]:
    """Evaluate questions grouped by db_id (one DB at a time). Stops at max_cost."""
    by_db: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        by_db[str(q["db_id"])].append(q)

    records: list[EvalRecord] = []
    for db_id in sorted(by_db):
        for q in by_db[db_id]:
            record = evaluate_question(q, client=client, model=model, settings=settings)
            records.append(record)
            if on_record is not None:
                on_record(record)
            if max_cost is not None and _estimated_cost(client, model) > max_cost:
                print(f"Reached max-cost ${max_cost}; stopping early at {len(records)} questions.")
                return records
    return records


def _load_done_ids() -> set[int]:
    if not PARTIAL_PATH.exists():
        return set()
    done: set[int] = set()
    for line in PARTIAL_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            done.add(int(json.loads(line)["question_id"]))
    return done


def _run_clarification_pass(
    client: LLMClient, model: str, settings: Settings
) -> list[LabeledResult]:
    labeled = json.loads(LABELED_PATH.read_text(encoding="utf-8"))
    schema_context = build_schema_card(settings.demo_db_path)
    semantic_context = render_semantic_layer()
    out: list[LabeledResult] = []
    for item in labeled["questions"]:
        report = detect_ambiguity(
            str(item["question"]),
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context=semantic_context,
        )
        out.append(
            LabeledResult(ambiguous=bool(item["ambiguous"]), flagged=report.needs_clarification)
        )
    return out


def _aggregate(
    records: list[EvalRecord], labeled: list[LabeledResult], model: str, k: int, cost: float
) -> dict[str, Any]:
    answered = [r for r in records if not r["clarified"] and r["confidence_score"] is not None]
    confs = [r["confidence_score"] for r in answered if r["confidence_score"] is not None]
    correct = [r["correct"] for r in answered if r["confidence_score"] is not None]

    # Calibration: split answered records into train/test, fit on train, evaluate on test.
    split = int(len(confs) * (1 - TEST_FRACTION))
    train_c, train_y = confs[:split], correct[:split]
    test_c, test_y = confs[split:], correct[split:]
    xs, ys = isotonic_fit(train_c, train_y)
    cmap = build_map(xs, ys)
    test_calibrated = [cmap.apply(c) for c in test_c]

    clar = clarification_precision_recall(labeled)
    abl = compute_ablation(records)

    return {
        "metadata": {
            "model": model,
            "k": k,
            "n_questions": len(records),
            "n_answered": len(answered),
            "estimated_cost_usd": round(cost, 4),
            "eval_peak_rss_mb": round(psutil.Process().memory_info().rss / (1024 * 1024), 1),
        },
        "accuracy": {
            "execution_accuracy": execution_accuracy(records),
            "answered_accuracy": answered_accuracy(records),
            "clarification_rate": clarification_rate(records),
            "semantic_error_rate": semantic_error_rate(records),
        },
        "confidently_wrong": {
            "threshold": CONFIDENT_THRESHOLD,
            "with_trust": confidently_wrong_rate(records),
            "baseline": baseline_confidently_wrong_rate(records),
            "absolute_reduction": abl.absolute_reduction,
            "relative_reduction": abl.relative_reduction,
        },
        "calibration": {
            "test_n": len(test_c),
            "brier_raw": brier_score(test_c, test_y),
            "brier_calibrated": brier_score(test_calibrated, test_y),
            "ece_raw": expected_calibration_error(test_c, test_y),
            "ece_calibrated": expected_calibration_error(test_calibrated, test_y),
            "reliability_raw": [dataclasses.asdict(b) for b in reliability_bins(confs, correct)],
        },
        "clarification": dataclasses.asdict(clar),
        "calibration_map": {"x": xs, "y": ys},
        "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the BIRD dev eval (pinned subset).")
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-cost", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true", help="No API calls (stub client).")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subset = json.loads(SUBSET_PATH.read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = sorted(
        subset["questions"], key=lambda q: int(q["question_id"])
    )
    if args.limit is not None:
        questions = questions[: args.limit]

    done = _load_done_ids()
    pending = [q for q in questions if int(q["question_id"]) not in done]
    print(f"{len(questions)} subset questions; {len(done)} already done; {len(pending)} to run.")

    settings = dataclasses.replace(
        get_settings(), self_consistency_samples=args.k, generation_model=args.model
    )
    client: LLMClient = DryRunClient() if args.dry_run else build_client()

    with PARTIAL_PATH.open("a", encoding="utf-8") as partial:

        def persist(record: EvalRecord) -> None:
            partial.write(json.dumps(record) + "\n")
            partial.flush()

        run_subset(
            pending,
            client=client,
            model=args.model,
            settings=settings,
            max_cost=args.max_cost,
            on_record=persist,
        )

    # Reload the full record set (resumed + new) for aggregation.
    records: list[EvalRecord] = [
        json.loads(line)
        for line in PARTIAL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    labeled = _run_clarification_pass(client, args.model, settings)
    cost = _estimated_cost(client, args.model)
    report = _aggregate(records, labeled, args.model, args.k, cost)

    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    wrote_map = write_calibration_map(
        settings.calibration_path, report["calibration_map"]["x"], report["calibration_map"]["y"]
    )
    print(f"Wrote {RESULTS_PATH} ({len(records)} records). Calibrated map written: {wrote_map}")
    print(
        f"  execution_accuracy={report['accuracy']['execution_accuracy']:.3f} "
        f"semantic_error={report['accuracy']['semantic_error_rate']:.3f}"
    )
    print(
        f"  confidently_wrong with_trust={report['confidently_wrong']['with_trust']:.3f} "
        f"baseline={report['confidently_wrong']['baseline']:.3f}"
    )
    print(f"  estimated_cost=${cost:.2f}")


if __name__ == "__main__":
    main()
