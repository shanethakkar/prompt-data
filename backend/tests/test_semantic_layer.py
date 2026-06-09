"""Tests for the semantic layer renderer."""

from __future__ import annotations

from backend.app.semantic_layer import render_semantic_layer


def test_render_includes_core_terms() -> None:
    text = render_semantic_layer()
    assert "revenue" in text
    assert "SUM(order_items.price)" in text
    assert "customer_unique_id" in text
    assert "order_status = 'delivered'" in text


def test_render_includes_notes() -> None:
    text = render_semantic_layer()
    # The customer mapping carries a clarifying note.
    assert "per-order" in text
