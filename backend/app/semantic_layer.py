"""Business-term to column/metric definitions.

Vague business language ("revenue", "a customer", "delivered") maps to concrete
SQL here, in one readable place, rather than being buried in the prompt. The
generator is told to prefer these resolutions, and in Phase 2 each resolution it
relied on becomes a surfaced assumption.

Keep this a plain, documented config. Add a mapping when a term is ambiguous
enough that the model would otherwise guess.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TermMapping:
    """One business term and how it resolves against the Olist schema."""

    term: str
    english: str
    sql_expression: str
    notes: str = ""


# Seeded from SPEC Section 6. Order is presentation order in the prompt.
SEMANTIC_LAYER: tuple[TermMapping, ...] = (
    TermMapping(
        term="revenue",
        english="product revenue, excluding freight",
        sql_expression="SUM(order_items.price)",
        notes="Use freight_value only when the question says 'spend' or 'including shipping'.",
    ),
    TermMapping(
        term="spend",
        english="customer spend, including freight",
        sql_expression="SUM(order_items.price + order_items.freight_value)",
    ),
    TermMapping(
        term="a customer",
        english="a distinct real-world customer",
        sql_expression="customers.customer_unique_id",
        notes="customer_id is per-order; customer_unique_id identifies the person across orders.",
    ),
    TermMapping(
        term="delivered",
        english="orders that reached the customer",
        sql_expression="orders.order_status = 'delivered'",
    ),
    TermMapping(
        term="order count",
        english="number of distinct orders",
        sql_expression="COUNT(DISTINCT orders.order_id)",
    ),
    TermMapping(
        term="average review score",
        english="mean review rating, 1 to 5",
        sql_expression="AVG(order_reviews.review_score)",
    ),
)


def render_semantic_layer(layer: tuple[TermMapping, ...] = SEMANTIC_LAYER) -> str:
    """Render the semantic layer as a prompt-injectable text block."""
    lines = ["Business term resolutions (prefer these when the question uses the term):"]
    for m in layer:
        line = f"- {m.term}: {m.english} -> {m.sql_expression}"
        if m.notes:
            line += f"  ({m.notes})"
        lines.append(line)
    return "\n".join(lines)
