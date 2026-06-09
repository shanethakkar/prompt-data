"""Read-only, SELECT-only SQL execution sandbox for Prompt Data.

This module is the prompt-injection backstop. Regardless of what the LLM emits,
only a single read-only SELECT ever reaches the database. The security model is
belt-and-suspenders, from outermost to innermost:

  1. sqlglot AST validation: parse the SQL and reject anything that is not a
     single SELECT (CTEs included). Reject load_extension() and friends. The
     validator FAILS CLOSED: any parse error or unexpected node becomes a
     ValidationError and the query never touches the DB.
  2. LIMIT injection: inject LIMIT 500 if absent, clamp it if it exceeds 500.
  3. Read-only SQLite connection via URI mode (file:path?mode=ro): the OS opens
     the file O_RDONLY, so even a hypothetical validator bypass cannot write.
  4. Statement timeout: SQLite has no native query timeout, so a threading.Timer
     calls conn.interrupt() to abort a long-running query.

This module must never import pandas/numpy/torch. See test_server_rss.py.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import expressions as exp

DEFAULT_LIMIT: int = 500
DEFAULT_TIMEOUT_SECONDS: float = 10.0

# Statement root types that are never allowed. Verified against sqlglot 25:
# ATTACH parses as exp.Attach and PRAGMA as exp.Pragma (not exp.Command), so
# both are listed explicitly. exp.Command is the catch-all for anything sqlglot
# does not model as a typed node.
_FORBIDDEN_ROOT_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Attach,
    exp.Pragma,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Command,
)

# Function names rejected anywhere in the AST. load_extension is the SQLite
# escape hatch to arbitrary native code; writefile/edit are shell extensions.
_FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset({"load_extension", "writefile", "edit"})


class ValidationError(Exception):
    """Raised when a query fails SELECT-only validation.

    Carries a human-readable reason. When this is raised, no SQL has been sent
    to the database.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass
class ExecutionResult:
    """Outcome of a validated query execution."""

    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count: int
    sql_executed: str
    timed_out: bool = False


def validate_and_inject(sql: str, default_limit: int = DEFAULT_LIMIT) -> str:
    """Validate that sql is a single safe SELECT and return it with a LIMIT applied.

    Raises ValidationError on anything that is not a single read-only SELECT,
    on multi-statement input, on forbidden functions, or on a parse error.
    Never lets a sqlglot exception escape: it is wrapped as ValidationError so
    the caller has a single failure mode to handle (fail closed).
    """
    stripped = sql.strip()
    if not stripped:
        raise ValidationError("Empty query.")

    # parse() (plural) returns every statement. parse_one() would silently drop
    # everything after the first, hiding "SELECT 1; DROP TABLE t".
    try:
        statements = sqlglot.parse(stripped, dialect="sqlite")
    except Exception as exc:
        raise ValidationError(f"Parse error: {exc}") from exc

    if not statements:
        raise ValidationError("No statement parsed.")
    if len(statements) > 1:
        raise ValidationError(
            f"Multi-statement query rejected ({len(statements)} statements). "
            "Only a single SELECT is allowed."
        )

    statement = statements[0]
    if statement is None:
        raise ValidationError("Parse produced a null statement.")

    if isinstance(statement, _FORBIDDEN_ROOT_TYPES):
        raise ValidationError(
            f"Statement type '{type(statement).__name__}' is not permitted. Only SELECT."
        )

    # A CTE (WITH ... SELECT) parses with exp.Select as its root, so this single
    # check covers both plain SELECTs and CTEs.
    if not isinstance(statement, exp.Select):
        raise ValidationError(
            f"Statement type '{type(statement).__name__}' is not permitted. Only SELECT."
        )

    for func in statement.find_all(exp.Anonymous):
        name = func.this
        if isinstance(name, str) and name.lower() in _FORBIDDEN_FUNCTIONS:
            raise ValidationError(f"Forbidden function '{name}' in query.")

    # Inject or clamp the LIMIT. .limit() returns a new node, so reassign.
    # The Limit node stores its value under the "expression" arg, not "this".
    existing_limit = statement.args.get("limit")
    if existing_limit is None:
        statement = statement.limit(default_limit)
    else:
        limit_value = existing_limit.args.get("expression")
        # Clamp a numeric limit that exceeds the cap. A non-numeric or absent
        # limit value is replaced with the cap outright, failing safe.
        if isinstance(limit_value, exp.Literal) and limit_value.is_number:
            if int(limit_value.this) > default_limit:
                statement = statement.limit(default_limit)
        else:
            statement = statement.limit(default_limit)

    # pretty=True formats the validated query across indented lines so the UI can show the
    # exact executed SQL in a readable, multi-line form. SQLite runs multi-line SQL identically.
    return statement.sql(dialect="sqlite", pretty=True)


def _open_readonly(db_path: str) -> sqlite3.Connection:
    """Open db_path read-only via SQLite URI mode.

    The mode=ro parameter makes SQLite open the file O_RDONLY at the VFS layer:
    any write is rejected by the engine itself. check_same_thread=False is
    required because the timeout callback runs in the timer thread.
    """
    # SQLite URIs need forward slashes even on Windows (C:\x -> C:/x).
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


def execute_query(
    sql: str,
    db_path: str,
    default_limit: int = DEFAULT_LIMIT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ExecutionResult:
    """Validate, inject a LIMIT, and execute sql read-only against db_path.

    Raises ValidationError for SQL that fails validation (before any DB contact).
    Raises sqlite3.Error for genuine database errors (e.g. unknown column).
    A timeout is not raised: the result is returned with timed_out=True.
    """
    final_sql = validate_and_inject(sql, default_limit)

    conn = _open_readonly(db_path)
    timed_out = False
    timer: threading.Timer | None = None

    def _interrupt() -> None:
        nonlocal timed_out
        timed_out = True
        conn.interrupt()

    try:
        timer = threading.Timer(timeout_seconds, _interrupt)
        timer.start()
        cursor = conn.execute(final_sql)
        columns = [desc[0] for desc in cursor.description or []]
        rows: list[tuple[Any, ...]] = cursor.fetchall()
    except sqlite3.OperationalError:
        # conn.interrupt() surfaces as OperationalError("interrupted"). Only
        # swallow it when our timer fired; re-raise genuine operational errors.
        if timed_out:
            return ExecutionResult(
                columns=[],
                rows=[],
                row_count=0,
                sql_executed=final_sql,
                timed_out=True,
            )
        raise
    finally:
        if timer is not None:
            timer.cancel()
        conn.close()

    return ExecutionResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        sql_executed=final_sql,
        timed_out=timed_out,
    )
