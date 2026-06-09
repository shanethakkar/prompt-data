"""Tests for deterministic assumption extraction (pure, no LLM/DB)."""

from __future__ import annotations

from backend.app.pipeline.assumptions import extract_assumptions

_SQL = (
    "SELECT t.product_category_name_english, SUM(oi.price) AS revenue "
    "FROM order_items AS oi "
    "JOIN products AS p ON oi.product_id = p.product_id "
    "JOIN product_category_name_translation AS t "
    "ON p.product_category_name = t.product_category_name "
    "WHERE oi.price > 10 "
    "GROUP BY t.product_category_name_english "
    "ORDER BY revenue DESC LIMIT 500"
)


def test_extracts_tables() -> None:
    a = extract_assumptions(_SQL)
    assert a.tables == [
        "order_items",
        "product_category_name_translation",
        "products",
    ]


def test_extracts_joins() -> None:
    a = extract_assumptions(_SQL)
    assert len(a.joins) == 2
    assert any("ON oi.product_id = p.product_id" in j for j in a.joins)


def test_extracts_filters_group_and_limit() -> None:
    a = extract_assumptions(_SQL)
    assert a.filters == ["oi.price > 10"]
    assert a.group_by == ["t.product_category_name_english"]
    assert a.row_limit == 500


def test_splits_anded_filters() -> None:
    sql = "SELECT 1 AS n FROM orders WHERE order_status = 'delivered' AND order_id > 'x' LIMIT 5"
    a = extract_assumptions(sql)
    assert a.filters == ["order_status = 'delivered'", "order_id > 'x'"]


def test_matches_revenue_term_despite_alias() -> None:
    # SUM(oi.price) should match the revenue mapping (SUM(order_items.price)).
    a = extract_assumptions(_SQL)
    assert any(m.startswith("revenue ->") for m in a.term_mappings)


def test_matches_delivered_term() -> None:
    sql = (
        "SELECT COUNT(DISTINCT order_id) AS n FROM orders WHERE order_status = 'delivered' LIMIT 5"
    )
    a = extract_assumptions(sql)
    assert any(m.startswith("delivered ->") for m in a.term_mappings)
    assert any(m.startswith("order count ->") for m in a.term_mappings)


def test_no_false_spend_match() -> None:
    # Only price present (no freight_value), so 'spend' must not match.
    a = extract_assumptions(_SQL)
    assert not any(m.startswith("spend ->") for m in a.term_mappings)
