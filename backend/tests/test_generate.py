"""Tests for generation and the self-correction loop (mocked LLM)."""

from __future__ import annotations

from backend.app.config import Settings
from backend.app.pipeline.generate import (
    SqlGeneration,
    build_system_prompt,
    generate_sql,
    generate_with_self_correction,
)
from backend.tests.conftest import FakeLLMClient

_GOOD_SQL = (
    "SELECT product_category_name, SUM(price) AS revenue "
    "FROM order_items JOIN products USING (product_id) "
    "GROUP BY product_category_name ORDER BY revenue DESC"
)


def test_generate_sql_passes_model_and_format_and_returns_parsed(fixture_db: str) -> None:
    client = FakeLLMClient([SqlGeneration(sql=_GOOD_SQL, explanation="Revenue by category.")])
    out = generate_sql(
        "revenue by category",
        client=client,
        model="claude-sonnet-4-6",
        schema_context="<schema>",
        semantic_context="<semantic>",
    )
    assert out.sql == _GOOD_SQL
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-4-6"
    assert call["output_format"] is SqlGeneration
    assert call["temperature"] == 0.0
    # The stable system prompt carries the rules + injected context.
    assert "single read-only" in str(call["system"]).lower()
    assert "<schema>" in str(call["system"])


def test_system_prompt_contains_cte_alias_rule() -> None:
    prompt = build_system_prompt("S", "L")
    assert "WITH c(n)" in prompt  # the forbidden form is shown as a negative example


def test_no_correction_when_first_query_succeeds(fixture_db: str, test_settings: Settings) -> None:
    client = FakeLLMClient([SqlGeneration(sql=_GOOD_SQL, explanation="ok")])
    result = generate_with_self_correction(
        "revenue by category",
        client=client,
        model="claude-sonnet-4-6",
        db_path=fixture_db,
        schema_context="s",
        semantic_context="l",
        settings=test_settings,
    )
    assert result.error is None
    assert result.execution is not None
    assert result.attempts == 1
    assert result.self_correction_fired is False


def test_self_correction_on_validation_error(fixture_db: str, test_settings: Settings) -> None:
    client = FakeLLMClient(
        [
            SqlGeneration(sql="DROP TABLE products", explanation="bad"),
            SqlGeneration(sql=_GOOD_SQL, explanation="good"),
        ]
    )
    result = generate_with_self_correction(
        "revenue by category",
        client=client,
        model="claude-sonnet-4-6",
        db_path=fixture_db,
        schema_context="s",
        semantic_context="l",
        settings=test_settings,
    )
    assert result.error is None
    assert result.execution is not None
    assert result.attempts == 2
    assert result.self_correction_fired is True
    # The repair turn carried the validator's rejection reason.
    assert "validator" in str(client.calls[1]["user"]).lower()


def test_self_correction_on_sqlite_error(fixture_db: str, test_settings: Settings) -> None:
    client = FakeLLMClient(
        [
            SqlGeneration(sql="SELECT no_such_column FROM products", explanation="bad"),
            SqlGeneration(sql=_GOOD_SQL, explanation="good"),
        ]
    )
    result = generate_with_self_correction(
        "revenue by category",
        client=client,
        model="claude-sonnet-4-6",
        db_path=fixture_db,
        schema_context="s",
        semantic_context="l",
        settings=test_settings,
    )
    assert result.error is None
    assert result.self_correction_fired is True
    assert "sqlite" in str(client.calls[1]["user"]).lower()


def test_exhaustion_returns_error(fixture_db: str, test_settings: Settings) -> None:
    # 1 initial + 2 repairs = 3 attempts, all invalid.
    client = FakeLLMClient(
        [SqlGeneration(sql="DROP TABLE products", explanation="bad") for _ in range(3)]
    )
    result = generate_with_self_correction(
        "revenue by category",
        client=client,
        model="claude-sonnet-4-6",
        db_path=fixture_db,
        schema_context="s",
        semantic_context="l",
        settings=test_settings,
    )
    assert result.execution is None
    assert result.error is not None
    assert result.attempts == 3
