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
from backend.app.pipeline.ambiguity import detect_ambiguity
from backend.app.pipeline.assumptions import Assumptions, extract_assumptions
from backend.app.pipeline.confidence import (
    Confidence,
    compute_confidence,
    load_calibration_map,
    self_consistency,
)
from backend.app.pipeline.generate import SelfCorrectionResult, generate_with_self_correction
from backend.app.pipeline.route import select_model
from backend.app.pipeline.schema import build_schema_card, select_schema_context
from backend.app.semantic_layer import render_semantic_layer

# Tokens that mark a column as time-valued for the chart heuristic.
_TIME_HINTS = ("date", "timestamp", "_ts", "month", "year", "day")

# Phase 1 uses the full schema (no retrieval), so retrieval contributes no
# uncertainty. Phase 3 replaces this with the real top-k retrieval score.
_RETRIEVAL_SCORE_PLACEHOLDER = 1.0


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


def _contexts(question: str, settings: Settings) -> tuple[str, str, str]:
    """Build (schema_context, semantic_context, model) for a question."""
    card = build_schema_card(settings.demo_db_path)
    return select_schema_context(question, card), render_semantic_layer(), select_model(question)


def _to_answer_result(question: str, result: SelfCorrectionResult) -> AnswerResult:
    """Map a generation result onto the presentation-facing AnswerResult."""
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


def answer_question(
    question: str,
    *,
    client: LLMClient,
    settings: Settings | None = None,
) -> AnswerResult:
    """Generation-only pipeline (no trust layer). Used by respond() and directly in tests."""
    settings = settings or get_settings()
    schema_context, semantic_context, model = _contexts(question, settings)
    result = generate_with_self_correction(
        question,
        client=client,
        model=model,
        db_path=settings.demo_db_path,
        schema_context=schema_context,
        semantic_context=semantic_context,
        settings=settings,
    )
    return _to_answer_result(question, result)


@dataclass
class Clarification:
    """A targeted clarifying question returned instead of an answer."""

    question: str
    options: list[str]
    dimensions: list[str]


@dataclass
class TrustedResponse:
    """The trust-layer response: either a clarification or an answer with assumptions/confidence."""

    question: str
    kind: str  # "answer" | "clarification"
    clarification: Clarification | None = None
    answer: AnswerResult | None = None
    assumptions: Assumptions | None = None
    confidence: Confidence | None = None


def respond(
    question: str,
    *,
    client: LLMClient,
    settings: Settings | None = None,
    clarification_answer: str | None = None,
) -> TrustedResponse:
    """Full trust-layer pipeline: clarify if ambiguous, else answer with assumptions/confidence."""
    settings = settings or get_settings()
    schema_context, semantic_context, model = _contexts(question, settings)

    # Ambiguity gate, unless the user already answered a prior clarifying question.
    if not clarification_answer:
        report = detect_ambiguity(
            question,
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context=semantic_context,
        )
        if report.needs_clarification:
            return TrustedResponse(
                question=question,
                kind="clarification",
                clarification=Clarification(
                    question=report.clarifying_question or "Could you clarify your question?",
                    options=report.options,
                    dimensions=report.dimensions,
                ),
            )

    effective_question = (
        question
        if not clarification_answer
        else f"{question}\n\nClarification: {clarification_answer}"
    )
    result = generate_with_self_correction(
        effective_question,
        client=client,
        model=model,
        db_path=settings.demo_db_path,
        schema_context=schema_context,
        semantic_context=semantic_context,
        settings=settings,
    )
    answer = _to_answer_result(question, result)

    if result.execution is None:
        return TrustedResponse(question=question, kind="answer", answer=answer)

    assumptions = extract_assumptions(result.sql)
    agreement, k = self_consistency(
        effective_question,
        client=client,
        model=model,
        db_path=settings.demo_db_path,
        schema_context=schema_context,
        semantic_context=semantic_context,
        settings=settings,
        primary_execution=result.execution,
    )
    confidence = compute_confidence(
        agreement=agreement,
        samples=k,
        self_correction_fired=result.self_correction_fired,
        retrieval_score=_RETRIEVAL_SCORE_PLACEHOLDER,
        calibration=load_calibration_map(settings.calibration_path),
    )
    return TrustedResponse(
        question=question,
        kind="answer",
        answer=answer,
        assumptions=assumptions,
        confidence=confidence,
    )
