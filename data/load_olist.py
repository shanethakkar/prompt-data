"""Offline ETL: load the nine Olist CSVs from data/raw/olist/ into data/demo.db.

Idempotent: every run drops and rebuilds all tables cleanly. Uses pandas for CSV
ingestion. pandas is acceptable here because this is an offline batch script that
is never imported by the server process (see the 4 GB RAM constraint in CLAUDE.md).

Run:  uv run python data/load_olist.py   (or: make load-db)

Data-quality notes baked into the schema (verified against the raw CSVs, see
docs/DECISIONS.md):
  - review_id is NOT unique (814 duplicate rows), so order_reviews is a rowid
    table with indexes rather than a review_id primary key.
  - Two product categories (pc_gamer, portateis_cozinha_e_preparadores_de_alimentos)
    have no row in the translation table. They are seeded with a passthrough
    English name so the products -> translation foreign key holds.
  - Zip code prefixes are stored as TEXT to preserve Brazilian CEP leading zeros.
"""

from __future__ import annotations

import argparse
import gc
import logging
import sqlite3
from pathlib import Path

import pandas as pd  # offline script only — never imported by the server

RAW_DIR = Path(__file__).parent / "raw" / "olist"
DB_PATH = Path(__file__).parent / "demo.db"

log = logging.getLogger("load_olist")

# Table creation order: parents before children so foreign keys resolve.
_CREATE_STATEMENTS: list[str] = [
    """
    CREATE TABLE product_category_name_translation (
        product_category_name         TEXT PRIMARY KEY,
        product_category_name_english TEXT
    )
    """,
    """
    CREATE TABLE customers (
        customer_id              TEXT PRIMARY KEY,
        customer_unique_id       TEXT NOT NULL,
        customer_zip_code_prefix TEXT NOT NULL,
        customer_city            TEXT NOT NULL,
        customer_state           TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE sellers (
        seller_id              TEXT PRIMARY KEY,
        seller_zip_code_prefix TEXT NOT NULL,
        seller_city            TEXT NOT NULL,
        seller_state           TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE products (
        product_id                 TEXT PRIMARY KEY,
        product_category_name      TEXT
            REFERENCES product_category_name_translation(product_category_name),
        product_name_lenght        INTEGER,
        product_description_lenght INTEGER,
        product_photos_qty         INTEGER,
        product_weight_g           INTEGER,
        product_length_cm          INTEGER,
        product_height_cm          INTEGER,
        product_width_cm           INTEGER
    )
    """,
    """
    CREATE TABLE orders (
        order_id                      TEXT PRIMARY KEY,
        customer_id                   TEXT NOT NULL REFERENCES customers(customer_id),
        order_status                  TEXT NOT NULL,
        order_purchase_timestamp      TEXT,
        order_approved_at             TEXT,
        order_delivered_carrier_date  TEXT,
        order_delivered_customer_date TEXT,
        order_estimated_delivery_date TEXT
    )
    """,
    """
    CREATE TABLE order_items (
        order_id            TEXT NOT NULL REFERENCES orders(order_id),
        order_item_id       INTEGER NOT NULL,
        product_id          TEXT REFERENCES products(product_id),
        seller_id           TEXT REFERENCES sellers(seller_id),
        shipping_limit_date TEXT,
        price               REAL NOT NULL,
        freight_value       REAL NOT NULL,
        PRIMARY KEY (order_id, order_item_id)
    )
    """,
    """
    CREATE TABLE order_payments (
        order_id             TEXT NOT NULL REFERENCES orders(order_id),
        payment_sequential   INTEGER NOT NULL,
        payment_type         TEXT NOT NULL,
        payment_installments INTEGER NOT NULL,
        payment_value        REAL NOT NULL,
        PRIMARY KEY (order_id, payment_sequential)
    )
    """,
    # review_id is not unique in the raw data, so this is a rowid table.
    """
    CREATE TABLE order_reviews (
        review_id               TEXT NOT NULL,
        order_id                TEXT NOT NULL REFERENCES orders(order_id),
        review_score            INTEGER NOT NULL,
        review_comment_title    TEXT,
        review_comment_message  TEXT,
        review_creation_date    TEXT NOT NULL,
        review_answer_timestamp TEXT NOT NULL
    )
    """,
    # geolocation has multiple rows per zip prefix, so it is a rowid table.
    """
    CREATE TABLE geolocation (
        geolocation_zip_code_prefix TEXT NOT NULL,
        geolocation_lat             REAL NOT NULL,
        geolocation_lng             REAL NOT NULL,
        geolocation_city            TEXT NOT NULL,
        geolocation_state           TEXT NOT NULL
    )
    """,
]

_INDEX_STATEMENTS: list[str] = [
    "CREATE INDEX idx_customers_unique_id ON customers(customer_unique_id)",
    "CREATE INDEX idx_orders_customer_id  ON orders(customer_id)",
    "CREATE INDEX idx_orders_status       ON orders(order_status)",
    "CREATE INDEX idx_orders_purchase_ts  ON orders(order_purchase_timestamp)",
    "CREATE INDEX idx_order_items_product ON order_items(product_id)",
    "CREATE INDEX idx_order_items_seller  ON order_items(seller_id)",
    "CREATE INDEX idx_order_reviews_order ON order_reviews(order_id)",
    "CREATE INDEX idx_order_reviews_id    ON order_reviews(review_id)",
    "CREATE INDEX idx_geolocation_zip     ON geolocation(geolocation_zip_code_prefix)",
    "CREATE INDEX idx_products_category   ON products(product_category_name)",
]

# Drop in reverse dependency order (children before parents).
_DROP_ORDER: list[str] = [
    "order_reviews",
    "order_payments",
    "order_items",
    "orders",
    "products",
    "sellers",
    "customers",
    "geolocation",
    "product_category_name_translation",
]

# (csv filename, table, dtype overrides, chunksize). Order = load order.
_LOAD_SPEC: list[tuple[str, str, dict[str, type], int | None]] = [
    ("product_category_name_translation.csv", "product_category_name_translation", {}, None),
    ("olist_customers_dataset.csv", "customers", {"customer_zip_code_prefix": str}, None),
    ("olist_sellers_dataset.csv", "sellers", {"seller_zip_code_prefix": str}, None),
    ("olist_products_dataset.csv", "products", {}, None),
    ("olist_orders_dataset.csv", "orders", {}, None),
    ("olist_order_items_dataset.csv", "order_items", {}, None),
    ("olist_order_payments_dataset.csv", "order_payments", {}, None),
    ("olist_order_reviews_dataset.csv", "order_reviews", {}, None),
    ("olist_geolocation_dataset.csv", "geolocation", {"geolocation_zip_code_prefix": str}, 50_000),
]

# Categories present in products but missing from the translation CSV. Seeded so
# the products.product_category_name foreign key holds. See docs/DECISIONS.md.
_MISSING_CATEGORIES: list[tuple[str, str]] = [
    ("pc_gamer", "pc_gamer"),
    (
        "portateis_cozinha_e_preparadores_de_alimentos",
        "portable_kitchen_and_food_preparers",
    ),
]


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a read-write connection with foreign key enforcement on."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def drop_tables(conn: sqlite3.Connection) -> None:
    for table in _DROP_ORDER:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


def create_tables(conn: sqlite3.Connection, slim: bool = False) -> None:
    for statement in _CREATE_STATEMENTS:
        if slim and "CREATE TABLE geolocation" in statement:
            continue
        conn.execute(statement)


def create_indexes(conn: sqlite3.Connection, slim: bool = False) -> None:
    for statement in _INDEX_STATEMENTS:
        if slim and "geolocation" in statement:
            continue
        conn.execute(statement)


def seed_missing_categories(conn: sqlite3.Connection) -> None:
    """Insert the two product categories that have no translation row."""
    conn.executemany(
        "INSERT OR IGNORE INTO product_category_name_translation "
        "(product_category_name, product_category_name_english) VALUES (?, ?)",
        _MISSING_CATEGORIES,
    )


def load_csv(
    conn: sqlite3.Connection,
    csv_path: Path,
    table_name: str,
    dtype: dict[str, type] | None,
    chunksize: int | None,
) -> int:
    """Load one CSV into a table. Returns the number of rows inserted.

    encoding='utf-8-sig' strips the BOM on the translation CSV. NA strings are
    kept as empty for nullable text columns. Large tables stream in chunks to
    keep peak memory low.
    """
    df = pd.read_csv(csv_path, dtype=dtype or None, encoding="utf-8-sig")
    rows = len(df)
    df.to_sql(
        table_name,
        conn,
        if_exists="append",
        index=False,
        chunksize=chunksize,
        method=None,
    )
    del df
    gc.collect()
    return rows


def verify(conn: sqlite3.Connection, slim: bool = False) -> None:
    """Run PRAGMA foreign_key_check and assert every loaded table has rows."""
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"Foreign key violations after load: {violations[:10]}")

    for table in _DROP_ORDER:
        if slim and table == "geolocation":
            continue
        (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if count == 0:
            raise RuntimeError(f"Table {table} is empty after load.")
        log.info("  %-36s %8d rows", table, count)


# Free-text columns dropped from the slim build (the demo uses review_score only).
_SLIM_DROP_COLUMNS: list[tuple[str, str]] = [
    ("order_reviews", "review_comment_title"),
    ("order_reviews", "review_comment_message"),
]


def load_all(db_path: Path = DB_PATH, raw_dir: Path = RAW_DIR, *, slim: bool = False) -> None:
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw CSV directory not found: {raw_dir}")

    log.info("Building %s from %s%s", db_path, raw_dir, " (slim)" if slim else "")
    conn = get_connection(db_path)
    try:
        drop_tables(conn)
        create_tables(conn, slim)

        for filename, table, dtype, chunksize in _LOAD_SPEC:
            if slim and table == "geolocation":
                continue
            rows = load_csv(conn, raw_dir / filename, table, dtype, chunksize)
            log.info("Loaded %-36s %8d rows", table, rows)
            if table == "product_category_name_translation":
                seed_missing_categories(conn)

        # Slim build: drop the large free-text review columns to fit the committed DB
        # under GitHub's 100 MB limit. Geolocation is skipped above. See docs/DECISIONS.md.
        if slim:
            for table, column in _SLIM_DROP_COLUMNS:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")

        create_indexes(conn, slim)
        conn.execute("ANALYZE")
        conn.commit()

        log.info("Verifying foreign keys and row counts:")
        verify(conn, slim)
        # Reclaim free pages so the committed slim DB is as small as possible.
        conn.execute("VACUUM")
        log.info("Done. demo.db is ready.")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Olist CSVs into SQLite.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument(
        "--slim",
        action="store_true",
        help="Deploy-sized build: omit the geolocation table and the review free-text columns "
        "so the committed data/demo.db stays under GitHub's 100 MB limit.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_all(db_path=args.db, raw_dir=args.raw, slim=args.slim)


if __name__ == "__main__":
    main()
