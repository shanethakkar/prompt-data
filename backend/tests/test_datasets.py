"""Tests for bring-your-own-data ingestion and the session store."""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from backend.app.config import Settings
from backend.app.datasets import (
    SessionStore,
    UploadError,
    ingest_csv,
    save_sqlite,
)


def _columns(db_path: str) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        return {row[1]: row[2] for row in conn.execute('PRAGMA table_info("data")')}
    finally:
        conn.close()


def test_ingest_csv_types_and_rows(test_settings: Settings, tmp_path: Path) -> None:
    content = b"Name,Age,Score,Note\nAlice,30,9.5,hi\nBob,25,8,\n"
    dest = str(tmp_path / "d.db")
    ingest_csv(content, dest, test_settings)

    cols = _columns(dest)
    assert cols == {"name": "TEXT", "age": "INTEGER", "score": "REAL", "note": "TEXT"}
    conn = sqlite3.connect(dest)
    try:
        rows = conn.execute('SELECT name, age, score, note FROM "data" ORDER BY name').fetchall()
    finally:
        conn.close()
    assert rows == [("Alice", 30, 9.5, "hi"), ("Bob", 25, 8.0, None)]


def test_ingest_csv_sanitizes_and_dedupes_columns(test_settings: Settings, tmp_path: Path) -> None:
    content = b"First Name,First Name,123,\nx,y,1,z\n"
    dest = str(tmp_path / "d.db")
    ingest_csv(content, dest, test_settings)
    assert list(_columns(dest)) == ["first_name", "first_name_2", "c_123", "col_4"]


def test_ingest_csv_rejects_oversize_and_wide(test_settings: Settings, tmp_path: Path) -> None:
    tiny = dataclasses.replace(test_settings, upload_max_csv_mb=0.000001)
    with pytest.raises(UploadError):
        ingest_csv(b"a,b\n1,2\n", str(tmp_path / "a.db"), tiny)

    narrow = dataclasses.replace(test_settings, upload_max_columns=2)
    with pytest.raises(UploadError):
        ingest_csv(b"a,b,c\n1,2,3\n", str(tmp_path / "b.db"), narrow)

    with pytest.raises(UploadError):
        ingest_csv(b"a,b\n", str(tmp_path / "c.db"), test_settings)  # header only


def test_ingest_csv_caps_rows(test_settings: Settings, tmp_path: Path) -> None:
    capped = dataclasses.replace(test_settings, upload_max_rows=2)
    content = b"n\n1\n2\n3\n4\n"
    dest = str(tmp_path / "d.db")
    ingest_csv(content, dest, capped)
    conn = sqlite3.connect(dest)
    try:
        assert conn.execute('SELECT COUNT(*) FROM "data"').fetchone()[0] == 2
    finally:
        conn.close()


def test_save_sqlite_validates(test_settings: Settings, tmp_path: Path, fixture_db: str) -> None:
    good = Path(fixture_db).read_bytes()
    dest = str(tmp_path / "ok.db")
    save_sqlite(good, dest, test_settings)
    assert Path(dest).exists()

    with pytest.raises(UploadError):
        save_sqlite(b"not a database", str(tmp_path / "bad.db"), test_settings)

    empty = sqlite3.connect(str(tmp_path / "src.db"))
    empty.close()
    empty_bytes = Path(tmp_path / "src.db").read_bytes()
    with pytest.raises(UploadError):  # valid SQLite header but no tables
        save_sqlite(empty_bytes, str(tmp_path / "empty.db"), test_settings)


class _Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _store(settings: Settings, tmp_path: Path, clock: _Clock) -> SessionStore:
    return SessionStore(dataclasses.replace(settings, upload_dir=str(tmp_path)), clock)


def test_session_store_ttl(test_settings: Settings, tmp_path: Path) -> None:
    clock = _Clock()
    store = _store(test_settings, tmp_path, clock)
    sid, path = store.new_path()
    Path(path).write_text("x")
    store.register(sid, path, "csv")
    assert store.get(sid) is not None

    clock.t += test_settings.session_ttl_minutes * 60 + 1
    assert store.get(sid) is None
    assert not Path(path).exists()  # expired file is deleted


def test_session_store_evicts_oldest(test_settings: Settings, tmp_path: Path) -> None:
    clock = _Clock()
    store = _store(dataclasses.replace(test_settings, max_sessions=2), tmp_path, clock)
    ids = []
    for _ in range(3):
        sid, path = store.new_path()
        Path(path).write_text("x")
        store.register(sid, path, "csv")
        ids.append(sid)
        clock.t += 1
    assert store.get(ids[0]) is None  # oldest evicted
    assert store.get(ids[2]) is not None
