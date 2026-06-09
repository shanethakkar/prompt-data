"""Tests for the SELECT-only execution sandbox.

Unit tests exercise validate_and_inject with no database. Integration tests run
execute_query against a temporary SQLite file created by the tmp_db fixture.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.app.pipeline.execute import (
    DEFAULT_LIMIT,
    ValidationError,
    execute_query,
    validate_and_inject,
)

# --------------------------------------------------------------------------- #
# Unit tests: validate_and_inject (no DB)                                     #
# --------------------------------------------------------------------------- #


def test_plain_select_passes() -> None:
    out = validate_and_inject("SELECT 1")
    assert "LIMIT" in out.upper()
    assert str(DEFAULT_LIMIT) in out


def test_cte_passes() -> None:
    out = validate_and_inject("WITH c AS (SELECT 1 AS n) SELECT n FROM c")
    assert "LIMIT" in out.upper()
    assert str(DEFAULT_LIMIT) in out


def test_subquery_passes() -> None:
    out = validate_and_inject("SELECT * FROM (SELECT 1 AS id) AS s")
    assert "LIMIT" in out.upper()


def test_limit_preserved_when_under_default() -> None:
    out = validate_and_inject("SELECT 1 LIMIT 10")
    assert "10" in out
    assert "500" not in out


def test_limit_clamped_when_over_default() -> None:
    out = validate_and_inject("SELECT 1 LIMIT 9999")
    assert "9999" not in out
    assert str(DEFAULT_LIMIT) in out


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET x = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "CREATE TABLE t (x INT)",
        "ALTER TABLE t ADD COLUMN y TEXT",
        "ATTACH DATABASE 'x.db' AS x",
        "PRAGMA table_info(t)",
    ],
)
def test_non_select_rejected(sql: str) -> None:
    with pytest.raises(ValidationError):
        validate_and_inject(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; DROP TABLE t",
        "SELECT 1; SELECT 2",
        "SELECT 1; INSERT INTO t VALUES (1)",
    ],
)
def test_multi_statement_rejected(sql: str) -> None:
    with pytest.raises(ValidationError):
        validate_and_inject(sql)


def test_load_extension_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_and_inject("SELECT load_extension('evil.so')")


@pytest.mark.parametrize("sql", ["", "   ", "\n\t "])
def test_empty_rejected(sql: str) -> None:
    with pytest.raises(ValidationError):
        validate_and_inject(sql)


def test_parse_error_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_and_inject("SELECT FROM WHERE")


def test_prompt_injection_attempt_rejected() -> None:
    # Classic injection: a trailing statement after a valid SELECT.
    with pytest.raises(ValidationError):
        validate_and_inject("SELECT * FROM customers; DROP TABLE customers")


# --------------------------------------------------------------------------- #
# Integration tests: execute_query against a temporary DB                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def tmp_db(tmp_path: Path) -> Iterator[str]:
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT, value REAL)")
    conn.executemany(
        "INSERT INTO widgets (id, name, value) VALUES (?, ?, ?)",
        [(1, "alpha", 1.5), (2, "beta", 2.5), (3, "gamma", 3.5)],
    )
    conn.commit()
    conn.close()
    yield db_path


def test_execute_basic_select(tmp_db: str) -> None:
    result = execute_query("SELECT * FROM widgets", tmp_db)
    assert result.row_count == 3
    assert result.timed_out is False


def test_execute_columns_returned(tmp_db: str) -> None:
    result = execute_query("SELECT id, name FROM widgets", tmp_db)
    assert result.columns == ["id", "name"]


def test_execute_limit_injected(tmp_db: str) -> None:
    result = execute_query("SELECT * FROM widgets", tmp_db)
    assert str(DEFAULT_LIMIT) in result.sql_executed


def test_execute_existing_limit_respected(tmp_db: str) -> None:
    result = execute_query("SELECT * FROM widgets LIMIT 2", tmp_db)
    assert result.row_count == 2


def test_execute_invalid_sql_raises(tmp_db: str) -> None:
    with pytest.raises(ValidationError):
        execute_query("DROP TABLE widgets", tmp_db)


def test_execute_write_blocked_by_validator(tmp_db: str) -> None:
    # The validator rejects this before the read-only connection is even opened.
    with pytest.raises(ValidationError):
        execute_query("INSERT INTO widgets (id, name, value) VALUES (4, 'x', 0)", tmp_db)


def test_execute_readonly_connection_blocks_writes(tmp_db: str) -> None:
    # Belt-and-suspenders: even if a write somehow reached the connection, the
    # mode=ro URI rejects it. We confirm by opening the same path read-only and
    # attempting a write directly.
    from backend.app.pipeline.execute import _open_readonly

    conn = _open_readonly(tmp_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO widgets (id, name, value) VALUES (4, 'x', 0)")
    finally:
        conn.close()


def test_execute_timeout(tmp_db: str) -> None:
    # COUNT(*) over a huge recursive CTE forces full materialization before any
    # row is produced, so the injected LIMIT 500 cannot short-circuit it. The
    # billion-row count cannot finish in 50 ms, so the timer interrupts it.
    # The recursion column is defined via "SELECT 1 AS n" rather than r(n): a
    # named-column table alias is dropped by sqlglot's round-trip (see
    # docs/DECISIONS.md), which would otherwise produce invalid SQL.
    slow = (
        "WITH RECURSIVE r AS ("
        "SELECT 1 AS n UNION ALL SELECT n + 1 FROM r WHERE n < 1000000000"
        ") SELECT COUNT(*) FROM r"
    )
    result = execute_query(slow, tmp_db, timeout_seconds=0.05)
    assert result.timed_out is True
