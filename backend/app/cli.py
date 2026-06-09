"""Command-line entry point for the pipeline.

    uv run python -m backend.app.cli "How many orders were delivered?"

Builds a real Anthropic client (needs ANTHROPIC_API_KEY) and prints the answer,
SQL, a compact result table, and the trust/metadata signals. This is the
live-smoke harness for the Phase 1 verification gate.
"""

from __future__ import annotations

import argparse
import dataclasses

from backend.app.config import get_settings
from backend.app.llm import build_client
from backend.app.pipeline.answer import AnswerResult, answer_question


def _format_table(columns: list[str], rows: list[tuple[object, ...]], limit: int = 20) -> str:
    if not columns:
        return "(no columns)"
    shown = rows[:limit]
    widths = [len(c) for c in columns]
    for row in shown:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    header = "  ".join(c.ljust(widths[i]) for i, c in enumerate(columns))
    sep = "  ".join("-" * widths[i] for i in range(len(columns)))
    body = "\n".join(
        "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) for row in shown
    )
    suffix = f"\n... ({len(rows) - limit} more rows)" if len(rows) > limit else ""
    return f"{header}\n{sep}\n{body}{suffix}"


def _render(result: AnswerResult) -> str:
    parts = [
        f"Q: {result.question}",
        "",
        f"Explanation: {result.explanation}",
        "",
        "SQL:",
        result.sql,
        "",
    ]
    if result.error:
        parts.append(f"ERROR: {result.error}")
    else:
        parts.append(f"Rows: {result.row_count}  |  Chart: {result.chart_type}")
        parts.append("")
        parts.append(_format_table(result.columns, result.rows))
    parts.append("")
    parts.append(
        f"[attempts={result.attempts} self_correction={result.self_correction_fired} "
        f"timed_out={result.timed_out}]"
    )
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask Verity a question about the Olist DB.")
    parser.add_argument("question", help="Natural-language question")
    parser.add_argument("--db", default=None, help="Override the demo DB path")
    args = parser.parse_args()

    settings = get_settings()
    if args.db:
        settings = dataclasses.replace(settings, demo_db_path=args.db)

    result = answer_question(args.question, client=build_client(), settings=settings)
    print(_render(result))


if __name__ == "__main__":
    main()
