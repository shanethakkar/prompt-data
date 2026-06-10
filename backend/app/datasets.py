"""Bring-your-own-data: ingest an uploaded CSV or SQLite file into a per-session database.

Stdlib only (no pandas), so the server holds the 4 GB ceiling. Queries against an uploaded
dataset still pass through the SELECT-only, read-only sandbox in execute.py, which remains the
security backstop. Sessions are process-local (single uvicorn worker) and expire by TTL.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.app.config import Settings

_SQLITE_MAGIC = b"SQLite format 3\x00"
_CSV_TABLE = "data"  # the single table a CSV is loaded into


def is_sqlite(content: bytes) -> bool:
    """True if the bytes start with the SQLite file header."""
    return content[:16] == _SQLITE_MAGIC


class UploadError(Exception):
    """Raised when an upload is rejected (too large, malformed, or unsupported)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class Session:
    id: str
    path: str
    created_at: float
    label: str


# --- CSV ingestion --------------------------------------------------------------------------


def _sanitize_columns(headers: list[str]) -> list[str]:
    out: list[str] = []
    for i, header in enumerate(headers):
        name = re.sub(r"\W+", "_", (header or "").strip().lower()).strip("_")
        if not name:
            name = f"col_{i + 1}"
        if name[0].isdigit():
            name = f"c_{name}"
        candidate, n = name, 1
        while candidate in out:
            n += 1
            candidate = f"{name}_{n}"
        out.append(candidate)
    return out


def _sniff_type(values: list[str]) -> str:
    """INTEGER / REAL / TEXT for a column, from its non-empty sample values."""
    seen_int = seen_real = False
    for value in values:
        try:
            int(value)
            seen_int = True
            continue
        except ValueError:
            pass
        try:
            float(value)
            seen_real = True
        except ValueError:
            return "TEXT"
    if seen_real:
        return "REAL"
    if seen_int:
        return "INTEGER"
    return "TEXT"


def _cast(value: str, sql_type: str) -> object:
    if value == "":
        return None
    if sql_type == "INTEGER":
        try:
            return int(value)
        except ValueError:
            return None
    if sql_type == "REAL":
        try:
            return float(value)
        except ValueError:
            return None
    return value


def ingest_csv(content: bytes, dest_path: str, settings: Settings) -> None:
    """Stream a CSV into a one-table ("data") SQLite at dest_path. Caps rows and columns."""
    if len(content) > settings.upload_max_csv_mb * 1024 * 1024:
        raise UploadError(f"CSV is larger than {settings.upload_max_csv_mb:g} MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise UploadError("The CSV is empty.") from exc
    if not header:
        raise UploadError("The CSV has no header row.")
    if len(header) > settings.upload_max_columns:
        raise UploadError(f"The CSV has more than {settings.upload_max_columns} columns.")

    columns = _sanitize_columns(header)
    rows: list[list[str]] = []
    for row in reader:
        if len(rows) >= settings.upload_max_rows:
            break
        # Pad/truncate ragged rows to the header width.
        rows.append((row + [""] * len(columns))[: len(columns)])
    if not rows:
        raise UploadError("The CSV has a header but no data rows.")

    types = [_sniff_type([r[i] for r in rows if r[i] != ""]) for i in range(len(columns))]
    quoted = ", ".join(f'"{c}" {t}' for c, t in zip(columns, types, strict=True))
    placeholders = ", ".join("?" for _ in columns)
    col_list = ", ".join(f'"{c}"' for c in columns)

    conn = sqlite3.connect(dest_path)
    try:
        conn.execute(f'CREATE TABLE "{_CSV_TABLE}" ({quoted})')
        conn.executemany(
            f'INSERT INTO "{_CSV_TABLE}" ({col_list}) VALUES ({placeholders})',
            ([_cast(v, t) for v, t in zip(row, types, strict=True)] for row in rows),
        )
        conn.commit()
    finally:
        conn.close()


def save_sqlite(content: bytes, dest_path: str, settings: Settings) -> None:
    """Validate that content is a SQLite database (with at least one table) and save it."""
    if len(content) > settings.upload_max_db_mb * 1024 * 1024:
        raise UploadError(f"Database is larger than {settings.upload_max_db_mb:g} MB.")
    if content[:16] != _SQLITE_MAGIC:
        raise UploadError("Not a valid SQLite database file.")
    Path(dest_path).write_bytes(content)
    conn = sqlite3.connect(f"file:{Path(dest_path).as_posix()}?mode=ro", uri=True)
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        conn.close()
    if not tables:
        Path(dest_path).unlink(missing_ok=True)
        raise UploadError("The database has no tables.")


# --- Session store --------------------------------------------------------------------------


class SessionStore:
    """Process-local registry of uploaded-dataset sessions with TTL and count eviction."""

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        self._settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}
        Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    def _delete(self, session: Session) -> None:
        Path(session.path).unlink(missing_ok=True)

    def _sweep_locked(self) -> None:
        ttl = self._settings.session_ttl_minutes * 60
        now = self._clock()
        for sid in [s.id for s in self._sessions.values() if now - s.created_at > ttl]:
            self._delete(self._sessions.pop(sid))
        # Evict the oldest beyond the cap.
        while len(self._sessions) > self._settings.max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s.created_at)
            self._delete(self._sessions.pop(oldest.id))

    def new_path(self) -> tuple[str, str]:
        """Allocate a session id and its file path (file not yet created)."""
        Path(self._settings.upload_dir).mkdir(parents=True, exist_ok=True)
        session_id = uuid.uuid4().hex
        return session_id, str(Path(self._settings.upload_dir) / f"{session_id}.db")

    def register(self, session_id: str, path: str, label: str) -> Session:
        session = Session(id=session_id, path=path, created_at=self._clock(), label=label)
        with self._lock:
            self._sessions[session_id] = session
            self._sweep_locked()
        return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            self._sweep_locked()
            return self._sessions.get(session_id)
