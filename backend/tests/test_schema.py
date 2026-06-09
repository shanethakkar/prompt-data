"""Tests for schema-card introspection."""

from __future__ import annotations

from backend.app.pipeline.schema import build_schema_card, schema_tables, select_schema_context


def test_card_lists_tables_and_columns(fixture_db: str) -> None:
    card = build_schema_card(fixture_db)
    assert "Table products" in card
    assert "Table order_items" in card
    assert "product_id" in card
    assert "freight_value" in card


def test_card_renders_foreign_keys(fixture_db: str) -> None:
    card = build_schema_card(fixture_db)
    assert "FOREIGN KEY (product_id) REFERENCES products(product_id)" in card


def test_card_renders_primary_key(fixture_db: str) -> None:
    card = build_schema_card(fixture_db)
    assert "PRIMARY KEY (order_id, order_item_id)" in card


def test_card_includes_known_descriptions(fixture_db: str) -> None:
    # products and order_items are known Olist tables, so descriptions render.
    card = build_schema_card(fixture_db)
    assert "per item" in card


def test_select_schema_context_returns_full_card_in_phase_1(fixture_db: str) -> None:
    card = build_schema_card(fixture_db)
    assert select_schema_context("any question", card) == card


def test_schema_tables_structured(fixture_db: str) -> None:
    tables = {t.name: t for t in schema_tables(fixture_db)}
    assert "order_items" in tables
    items = tables["order_items"]
    assert items.row_count > 0
    cols = {c.name: c for c in items.columns}
    assert cols["order_id"].primary_key is True
    assert "product_id -> products(product_id)" in items.foreign_keys
    assert tables["products"].description is not None
