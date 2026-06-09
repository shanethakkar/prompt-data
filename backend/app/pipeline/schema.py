"""Schema card: a compact description of the database for the prompt.

Structure (tables, columns, types, primary and foreign keys) is introspected
from the live database over a read-only connection, so the card never drifts
from what is actually in demo.db. One-line descriptions are hand-authored for
the Olist tables and merged in. The card doubles as the retrieval corpus in
Phase 3; for Phase 1 the whole card fits the prompt and is sent in full.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache

from backend.app.pipeline.execute import _open_readonly

# One-line descriptions per Olist table. Unknown tables (e.g. test fixtures or a
# bring-your-own DB) simply have no description line.
TABLE_DESCRIPTIONS: dict[str, str] = {
    "customers": "One row per order's customer. customer_unique_id identifies the person.",
    "orders": "One row per order, with status and the purchase/delivery timestamps.",
    "order_items": "One row per item within an order. price and freight_value are per item.",
    "order_payments": "Payment installments per order. One order can have several payment rows.",
    "order_reviews": "Customer reviews. review_id is NOT unique (some rows repeat).",
    "products": "Product catalog. Category names are Portuguese; join the translation table.",
    "sellers": "Marketplace sellers.",
    "geolocation": "Zip-prefix to lat/lng. Many rows per zip prefix; not a 1-to-1 lookup.",
    "product_category_name_translation": "Portuguese to English product category names.",
}

# Notes on individual columns whose meaning or spelling is not obvious.
COLUMN_NOTES: dict[tuple[str, str], str] = {
    ("products", "product_name_lenght"): "sic: misspelled in the source data",
    ("products", "product_description_lenght"): "sic: misspelled in the source data",
    ("orders", "order_status"): "e.g. 'delivered', 'shipped', 'canceled'",
}


def _table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def _render_table(conn: sqlite3.Connection, table: str) -> str:
    lines: list[str] = []
    description = TABLE_DESCRIPTIONS.get(table)
    header = f"Table {table}"
    if description:
        header += f" — {description}"
    lines.append(header)

    # Quote the table name: BIRD has tables named with reserved words (e.g. "order").
    quoted = '"' + table.replace('"', '""') + '"'

    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    columns = conn.execute(f"PRAGMA table_info({quoted})").fetchall()
    pk_cols = [c[1] for c in columns if c[5]]
    for col in columns:
        name, col_type = col[1], col[2] or "TEXT"
        note = COLUMN_NOTES.get((table, name))
        line = f"  {name} {col_type}"
        if note:
            line += f"  -- {note}"
        lines.append(line)

    if pk_cols:
        lines.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")

    # PRAGMA foreign_key_list: (id, seq, table, from, to, on_update, on_delete, match)
    fks = conn.execute(f"PRAGMA foreign_key_list({quoted})").fetchall()
    for fk in fks:
        ref_table, from_col, to_col = fk[2], fk[3], fk[4]
        lines.append(f"  FOREIGN KEY ({from_col}) REFERENCES {ref_table}({to_col})")

    return "\n".join(lines)


@lru_cache
def build_schema_card(db_path: str) -> str:
    """Introspect db_path read-only and render the full schema card."""
    conn = _open_readonly(db_path)
    try:
        blocks = [_render_table(conn, table) for table in _table_names(conn)]
    finally:
        conn.close()
    return "\n\n".join(blocks)


def select_schema_context(question: str, card: str) -> str:
    """Return the schema context for a question.

    Phase 1 returns the full card (the Olist schema fits the prompt). This is the
    seam for Phase 3 top-k retrieval over large or bring-your-own schemas.
    """
    _ = question
    return card
