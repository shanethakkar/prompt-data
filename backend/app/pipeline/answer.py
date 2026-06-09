"""Pipeline orchestrator.

Ties together schema context, the semantic layer, generation with self-correction,
and presentation. Returns a single AnswerResult that the CLI and the /ask endpoint
both render. The trust layer (assumptions, confidence) extends this in Phase 2.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
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

# A line chart implies a trend over continuous time. It is chosen when the x-axis column name is
# a continuous time unit, or its values look like dates/timestamps or a run of calendar years.
# "day"/"weekday"/"hour" are intentionally absent: those are categorical cycles (e.g. "day of
# week") that read better as bars, which was the source of mislabeled line charts.
_TIME_NAME_HINTS = ("date", "month", "year", "quarter", "timestamp", "_ts")
_DATE_VALUE = re.compile(r"^\s*\d{4}[-/]\d{1,2}([-/]\d{1,2})?([ T]\d{1,2}:\d{2})?\s*$")

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


def _is_year(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 1900 <= value <= 2100
    if isinstance(value, str) and re.fullmatch(r"\d{4}", value.strip()):
        return 1900 <= int(value) <= 2100
    return False


def _looks_temporal(col_name: str, values: list[Any]) -> bool:
    """True when the x-axis is a real time sequence (continuous time unit by name or by value)."""
    if any(token in col_name.lower() for token in _TIME_NAME_HINTS):
        return True
    sample = [v for v in values if v is not None][:24]
    if not sample:
        return False
    date_like = sum(1 for v in sample if isinstance(v, str) and _DATE_VALUE.match(v))
    if date_like >= max(2, int(len(sample) * 0.7)):
        return True
    return len(sample) >= 2 and all(_is_year(v) for v in sample)


def suggest_chart(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    """Heuristic chart type from the result shape and x-axis. Pure function.

    Two numeric-valued columns plot as a line only when the first column is a genuine time
    sequence; otherwise the x-axis is categorical (e.g. "day of week") and a bar fits better.
    """
    if not rows or not columns:
        return "none"
    if len(rows) == 1 and len(columns) == 1:
        return "stat"
    if len(columns) == 2 and _is_number(rows[0][1]):
        return "line" if _looks_temporal(columns[0], [row[0] for row in rows]) else "bar"
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


def respond_events(
    question: str,
    *,
    client: LLMClient,
    settings: Settings | None = None,
    clarification_answer: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Run the trust pipeline, yielding stage events then a terminal clarification/answer.

    Stage events ({"type":"stage","name","label"}) let the UI show the pipeline working step
    by step. Terminal events carry the dataclass objects directly; the SSE endpoint serializes
    them, and respond() drains this generator to build a TrustedResponse. One orchestration path.
    """
    settings = settings or get_settings()
    schema_context, semantic_context, model = _contexts(question, settings)

    # Ambiguity gate, unless the user already answered a prior clarifying question.
    if not clarification_answer:
        yield {"type": "stage", "name": "ambiguity", "label": "Checking the question for ambiguity"}
        report = detect_ambiguity(
            question,
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context=semantic_context,
        )
        if report.needs_clarification:
            yield {
                "type": "clarification",
                "clarification": Clarification(
                    question=report.clarifying_question or "Could you clarify your question?",
                    options=report.options,
                    dimensions=report.dimensions,
                ),
            }
            return

    effective_question = (
        question
        if not clarification_answer
        else f"{question}\n\nClarification: {clarification_answer}"
    )
    yield {"type": "stage", "name": "generating", "label": "Generating and running SQL"}
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
        yield {"type": "answer", "answer": answer, "assumptions": None, "confidence": None}
        return

    assumptions = extract_assumptions(result.sql)
    # Emit the answer (data, SQL, assumptions) immediately so it never waits on confidence;
    # confidence is scored next and streamed as its own event.
    yield {"type": "answer", "answer": answer, "assumptions": assumptions, "confidence": None}

    yield {"type": "stage", "name": "confidence", "label": "Scoring confidence"}
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
    # Re-emit the full answer, now scored. Using a second "answer" event (rather than a new
    # event type) keeps the stream backward-compatible: an older deployed frontend re-renders
    # the same answer with confidence instead of mishandling an unknown event and clearing it.
    yield {"type": "answer", "answer": answer, "assumptions": assumptions, "confidence": confidence}


def respond(
    question: str,
    *,
    client: LLMClient,
    settings: Settings | None = None,
    clarification_answer: str | None = None,
) -> TrustedResponse:
    """Drain respond_events into a single TrustedResponse (non-streaming callers)."""
    answer_event: dict[str, Any] | None = None
    clarification: Clarification | None = None
    for event in respond_events(
        question, client=client, settings=settings, clarification_answer=clarification_answer
    ):
        if event["type"] == "clarification":
            clarification = event["clarification"]
        elif event["type"] == "answer":
            answer_event = event  # the last answer event carries the scored confidence

    if clarification is not None:
        return TrustedResponse(question=question, kind="clarification", clarification=clarification)
    if answer_event is None:
        return TrustedResponse(question=question, kind="answer")
    return TrustedResponse(
        question=question,
        kind="answer",
        answer=answer_event["answer"],
        assumptions=answer_event["assumptions"],
        confidence=answer_event["confidence"],
    )
