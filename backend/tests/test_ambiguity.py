"""Tests for the ambiguity gate and the clarify branch of respond()."""

from __future__ import annotations

from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.pipeline.ambiguity import AmbiguityReport, detect_ambiguity
from backend.app.pipeline.answer import respond
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient

_REVENUE_SQL = (
    "SELECT product_category_name, SUM(price) AS revenue "
    "FROM order_items JOIN products USING (product_id) "
    "GROUP BY product_category_name ORDER BY revenue DESC"
)


def test_detect_ambiguity_returns_report_and_uses_temperature_zero(fixture_db: str) -> None:
    report = AmbiguityReport(needs_clarification=False)
    client = FakeLLMClient([report])
    out = detect_ambiguity(
        "how many orders",
        client=client,
        model="claude-sonnet-4-6",
        schema_context="<schema>",
        semantic_context="<semantic>",
    )
    assert out.needs_clarification is False
    call = client.calls[0]
    assert call["output_format"] is AmbiguityReport
    assert call["temperature"] == 0.0


def test_respond_returns_clarification_when_ambiguous(test_settings: Settings) -> None:
    client = FakeLLMClient(
        [
            AmbiguityReport(
                needs_clarification=True,
                dimensions=["metric"],
                clarifying_question="By revenue or by number of orders?",
                options=["by revenue", "by number of orders"],
            )
        ]
    )
    result = respond("top products", client=client, settings=test_settings)
    assert result.kind == "clarification"
    assert result.clarification is not None
    assert result.clarification.options == ["by revenue", "by number of orders"]
    assert result.answer is None
    # No generation happened: only the ambiguity call was made.
    assert len(client.calls) == 1


def test_respond_proceeds_when_clear(test_settings: Settings) -> None:
    # 1 ambiguity (clear) + primary + 2 self-consistency samples (K=3).
    responses: list[BaseModel] = [AmbiguityReport(needs_clarification=False)]
    responses += [
        SqlGeneration(sql=_REVENUE_SQL, explanation="revenue by category") for _ in range(3)
    ]
    result = respond("revenue by category", client=FakeLLMClient(responses), settings=test_settings)
    assert result.kind == "answer"
    assert result.answer is not None and result.answer.row_count == 2
    assert result.assumptions is not None
    assert result.confidence is not None and result.confidence.agreement == 1.0


def test_respond_with_clarification_answer_skips_gate(test_settings: Settings) -> None:
    # No AmbiguityReport queued: the gate must be skipped when an answer is supplied.
    responses: list[BaseModel] = [
        SqlGeneration(sql=_REVENUE_SQL, explanation="revenue") for _ in range(3)
    ]
    result = respond(
        "top products",
        client=FakeLLMClient(responses),
        settings=test_settings,
        clarification_answer="by revenue",
    )
    assert result.kind == "answer"
    assert result.assumptions is not None
