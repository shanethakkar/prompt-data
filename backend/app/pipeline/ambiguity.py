"""Ambiguity detection: decide whether to clarify before answering.

Before committing to a query, classify the question across five dimensions
(SPEC Section 8). If a dimension is genuinely underspecified, return one targeted
clarifying question with concrete options instead of guessing. Over-asking on
clear questions is a failure mode too, and is measured in Phase 3, so the prompt
errs toward answering unless ambiguity is real.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.llm import LLMClient

_DIMENSIONS = "metric | time_window | entity | grain | answerability"

_SYSTEM = f"""\
You are the ambiguity gate of a natural-language-to-SQL system for an Olist \
e-commerce SQLite database. Decide whether a question can be answered as-is or \
needs one clarifying question first.

Classify across these dimensions: {_DIMENSIONS}.
- metric: the measure is undefined or could mean different things (e.g. "top" by \
revenue vs by order count).
- time_window: a relative or vague period ("last quarter", "recently") with no fixed range.
- entity: which entity is meant is unclear (e.g. "customer" as person vs per-order id).
- grain: the aggregation level is unclear (per order, per item, per customer).
- answerability: the question asks for data not present in the schema below.

Rules:
- Flag ONLY genuine ambiguity. Most questions are answerable; do not over-ask. \
Reasonable defaults (the semantic layer) resolve many terms, so do not flag those.
- If you flag, set needs_clarification true, list the flagged dimensions, and give \
ONE minimal clarifying question with 2 to 4 concrete options.
- If the question is answerable, set needs_clarification false and leave the question \
null and options empty.
- Use plain ASCII punctuation in the question and options: hyphens, commas, colons. \
No em dashes or en dashes."""


class AmbiguityReport(BaseModel):
    """Structured verdict from the ambiguity gate."""

    needs_clarification: bool = Field(
        description="True only if genuine ambiguity blocks answering."
    )
    dimensions: list[str] = Field(
        default_factory=list, description="Flagged dimensions from the fixed set."
    )
    clarifying_question: str | None = Field(
        default=None, description="One minimal question; null if answerable."
    )
    options: list[str] = Field(
        default_factory=list, description="2 to 4 concrete options; empty if answerable."
    )


def detect_ambiguity(
    question: str,
    *,
    client: LLMClient,
    model: str,
    schema_context: str,
    semantic_context: str,
) -> AmbiguityReport:
    """One structured classification call. Deterministic (temperature 0)."""
    system = (
        f"{_SYSTEM}\n\n<schema>\n{schema_context}\n</schema>\n\n"
        f"<semantic_layer>\n{semantic_context}\n</semantic_layer>"
    )
    return client.generate_structured(
        model=model,
        system=system,
        user=f"Question: {question}",
        output_format=AmbiguityReport,
        temperature=0.0,
    )
