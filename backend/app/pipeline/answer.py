"""Pipeline orchestrator.

Ties together schema context, the semantic layer, generation with self-correction,
and presentation. Returns a single AnswerResult that the CLI and the /ask endpoint
both render. The trust layer (assumptions, confidence) extends this in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.llm import LLMClient
from backend.app.pipeline.generate import generate_with_self_correction
from backend.app.pipeline.route import select_model
from backend.app.pipeline.schema import build_schema_card, select_schema_context
from backend.app.semantic_layer import render_semantic_layer

# Tokens that mark a column as time-valued for the chart heuristic.
_TIME_HINTS = ("date", "timestamp", "_ts", "month", "year", "day")


@dataclass
class AnswerResult:
    """Everything the UI needs to render one answer."""

    question: str
    explanation: str
    sql: str
    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    chart_type: str
    self_correction_fired: bool
    attempts: int
    timed_out: bool
    error: str | None = field(default=None)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def suggest_chart(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Heuristic chart type from the result shape. Pure function."""
    if not rows or not columns:
        return "none"
    if len(rows) == 1 and len(columns) == 1:
        return "stat"
    if len(columns) == 2:
        first_is_time = any(hint in columns[0].lower() for hint in _TIME_HINTS)
        second_numeric = _is_number(rows[0][1])
        if second_numeric:
            return "line" if first_is_time else "bar"
    return "table"


def answer_question(
    question: str,
    *,
    client: LLMClient,
    settings: Settings | None = None,
) -> AnswerResult:
    """Run the full pipeline for one question."""
    settings = settings or get_settings()

    card = build_schema_card(settings.demo_db_path)
    schema_context = select_schema_context(question, card)
    semantic_context = render_semantic_layer()
    model = select_model(question)

    result = generate_with_self_correction(
        question,
        client=client,
        model=model,
        db_path=settings.demo_db_path,
        schema_context=schema_context,
        semantic_context=semantic_context,
        settings=settings,
    )

    execution = result.execution
    if execution is None:
        return AnswerResult(
            question=question,
            explanation=result.explanation,
            sql=result.sql,
            columns=[],
            rows=[],
            row_count=0,
            chart_type="none",
            self_correction_fired=result.self_correction_fired,
            attempts=result.attempts,
            timed_out=False,
            error=result.error,
        )

    return AnswerResult(
        question=question,
        explanation=result.explanation,
        sql=result.sql,
        columns=execution.columns,
        rows=execution.rows,
        row_count=execution.row_count,
        chart_type=suggest_chart(execution.columns, execution.rows),
        self_correction_fired=result.self_correction_fired,
        attempts=result.attempts,
        timed_out=execution.timed_out,
        error="Query timed out." if execution.timed_out else None,
    )
