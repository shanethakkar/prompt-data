"""Command-line entry point for the pipeline.

    uv run python -m backend.app.cli "How many orders were delivered?"

Builds a real Anthropic client (needs ANTHROPIC_API_KEY) and prints either a
clarifying question or the answer with its SQL, result table, assumptions, and
confidence. This is the live-smoke harness for the verification gate.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys

from backend.app.config import get_settings
from backend.app.llm import build_client
from backend.app.pipeline.answer import AnswerResult, TrustedResponse, respond
from backend.app.pipeline.assumptions import Assumptions
from backend.app.pipeline.confidence import Confidence


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


def _render_assumptions(a: Assumptions) -> str:
    lines = ["Assumptions:"]
    if a.term_mappings:
        lines.append(f"  terms:   {', '.join(a.term_mappings)}")
    lines.append(f"  tables:  {', '.join(a.tables) or '(none)'}")
    if a.joins:
        lines.append(f"  joins:   {'; '.join(a.joins)}")
    if a.filters:
        lines.append(f"  filters: {'; '.join(a.filters)}")
    if a.group_by:
        lines.append(f"  grain:   {', '.join(a.group_by)}")
    if a.row_limit is not None:
        lines.append(f"  limit:   {a.row_limit}")
    return "\n".join(lines)


def _render_confidence(c: Confidence) -> str:
    label = "calibrated" if c.calibrated else "provisional, uncalibrated"
    return f"Confidence: {c.score:.2f} ({label}) - {c.explanation}"


def _render_answer(answer: AnswerResult) -> str:
    parts = [f"Explanation: {answer.explanation}", "", "SQL:", answer.sql, ""]
    if answer.error:
        parts.append(f"ERROR: {answer.error}")
    else:
        parts.append(f"Rows: {answer.row_count}  |  Chart: {answer.chart_type}")
        parts.append("")
        parts.append(_format_table(answer.columns, answer.rows))
    parts.append("")
    parts.append(
        f"[attempts={answer.attempts} self_correction={answer.self_correction_fired} "
        f"timed_out={answer.timed_out}]"
    )
    return "\n".join(parts)


def _render(result: TrustedResponse) -> str:
    parts = [f"Q: {result.question}", ""]
    if result.kind == "clarification" and result.clarification is not None:
        c = result.clarification
        parts.append(f"Clarifying question: {c.question}")
        if c.dimensions:
            parts.append(f"  (ambiguous: {', '.join(c.dimensions)})")
        for i, opt in enumerate(c.options, 1):
            parts.append(f"  {i}. {opt}")
        parts.append("")
        parts.append('Re-run with --clarify "<your answer>" to proceed.')
        return "\n".join(parts)

    if result.answer is not None:
        parts.append(_render_answer(result.answer))
    if result.assumptions is not None:
        parts.append("")
        parts.append(_render_assumptions(result.assumptions))
    if result.confidence is not None:
        parts.append("")
        parts.append(_render_confidence(result.confidence))
    return "\n".join(parts)


def main() -> None:
    # Model output (and the schema) may contain non-ASCII; avoid cp1252 mojibake on Windows.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Ask Verity a question about the Olist DB.")
    parser.add_argument("question", help="Natural-language question")
    parser.add_argument("--db", default=None, help="Override the demo DB path")
    parser.add_argument("--clarify", default=None, help="Answer to a prior clarifying question")
    args = parser.parse_args()

    settings = get_settings()
    if args.db:
        settings = dataclasses.replace(settings, demo_db_path=args.db)

    result = respond(
        args.question,
        client=build_client(),
        settings=settings,
        clarification_answer=args.clarify,
    )
    print(_render(result))


if __name__ == "__main__":
    main()
