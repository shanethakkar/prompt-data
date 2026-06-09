"""Capture the /gallery contrast cards (offline, paid).

For each curated question, run BOTH pipelines over the Olist demo DB and store the
real outputs: the no-trust baseline (its actual SQL + result or error) and Prompt Data
(its clarification, or its answer with assumptions and calibrated confidence). Same
model, trust off vs on. Writes the committed eval/out/gallery.json the frontend renders.

    uv run python eval/run_gallery.py --model claude-sonnet-4-6 --k 3
    uv run python eval/run_gallery.py --dry-run        # no API
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.llm import AnthropicClient, LLMClient, build_client
from backend.app.pipeline.answer import TrustedResponse, respond
from backend.app.pipeline.execute import ValidationError, execute_query
from backend.app.pipeline.generate import generate_sql
from backend.app.pipeline.schema import build_schema_card
from backend.app.semantic_layer import render_semantic_layer
from eval.run_bird import PRICES, DryRunClient

OUT_DIR = Path(__file__).parent / "out"
RESULTS_PATH = OUT_DIR / "gallery.json"
QUESTIONS_PATH = Path(__file__).parent / "gallery_questions.json"
EVAL_ROW_CAP = 10000
DISPLAY_ROWS = 8  # cap rows stored per card for a compact gallery


def _load_curated() -> list[dict[str, str]]:
    """Curated showcase questions (data lives in gallery_questions.json)."""
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return list(data["questions"])


def _naive(
    question: str, *, client: LLMClient, model: str, schema_context: str, settings: Settings
) -> dict[str, Any]:
    """The no-trust baseline: one generation, executed through the sandbox."""
    sql = ""
    try:
        gen = generate_sql(
            question,
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context="",
            temperature=0.0,
        )
        sql = gen.sql
        execution = execute_query(
            sql,
            settings.demo_db_path,
            default_limit=EVAL_ROW_CAP,
            timeout_seconds=settings.sql_timeout_seconds,
        )
        return {
            "sql": sql,
            "columns": execution.columns,
            "rows": [list(r) for r in execution.rows[:DISPLAY_ROWS]],
            "row_count": execution.row_count,
            "error": "Query timed out." if execution.timed_out else None,
        }
    except ValidationError as exc:
        return {
            "sql": sql,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": f"Rejected by the read-only validator: {exc.reason}",
        }
    except sqlite3.Error as exc:
        return {
            "sql": sql,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": f"SQLite error: {exc}",
        }


def _serialize_verity(tr: TrustedResponse) -> dict[str, Any]:
    if tr.kind == "clarification" and tr.clarification is not None:
        return {"kind": "clarification", "clarification": dataclasses.asdict(tr.clarification)}
    answer = tr.answer
    answer_dict = dataclasses.asdict(answer) if answer else None
    if answer_dict and answer:
        answer_dict["rows"] = [list(r) for r in answer.rows[:DISPLAY_ROWS]]
    return {
        "kind": "answer",
        "answer": answer_dict,
        "assumptions": dataclasses.asdict(tr.assumptions) if tr.assumptions else None,
        "confidence": dataclasses.asdict(tr.confidence) if tr.confidence else None,
    }


def capture_card(
    item: dict[str, str], *, client: LLMClient, model: str, settings: Settings
) -> dict[str, Any]:
    schema_context = build_schema_card(settings.demo_db_path)
    _ = render_semantic_layer()  # Prompt Data uses it internally via respond()
    naive = _naive(
        item["question"],
        client=client,
        model=model,
        schema_context=schema_context,
        settings=settings,
    )
    verity = _serialize_verity(respond(item["question"], client=client, settings=settings))
    return {
        "id": item["id"],
        "category": item["category"],
        "question": item["question"],
        "takeaway": item["takeaway"],
        "naive": naive,
        "verity": verity,
    }


def _estimated_cost(client: LLMClient, model: str) -> float:
    if not isinstance(client, AnthropicClient):
        return 0.0
    in_price, out_price = PRICES.get(model, (0.0, 0.0))
    return client.input_tokens / 1e6 * in_price + client.output_tokens / 1e6 * out_price


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture the /gallery contrast cards.")
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    settings = dataclasses.replace(
        get_settings(), self_consistency_samples=args.k, generation_model=args.model
    )
    client: LLMClient = DryRunClient() if args.dry_run else build_client()

    curated = _load_curated()
    cards = [
        capture_card(item, client=client, model=args.model, settings=settings) for item in curated
    ]
    report = {
        "model": args.model,
        "generated": date.today().isoformat(),
        "estimated_cost_usd": round(_estimated_cost(client, args.model), 4),
        "cards": cards,
    }
    RESULTS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    clarified = sum(1 for c in cards if c["verity"]["kind"] == "clarification")
    cost = report["estimated_cost_usd"]
    print(f"Wrote {RESULTS_PATH}: {len(cards)} cards ({clarified} clarified), ${cost}")


if __name__ == "__main__":
    main()
