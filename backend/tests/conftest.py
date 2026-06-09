"""Shared fixtures for the Phase 1 pipeline tests.

The fake LLM client returns queued, pre-canned structured outputs, so tests are
deterministic and spend no tokens. The fixture DB is a tiny Olist-shaped SQLite
file in tmp_path; tests never touch the real (gitignored) demo.db.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import TypeVar, cast

import pytest
from pydantic import BaseModel

from backend.app.config import Settings

T = TypeVar("T", bound=BaseModel)


class FakeLLMClient:
    """Deterministic LLMClient for tests.

    Returns the next queued response whose type matches the requested
    output_format (falling back to plain FIFO if none match). Type-matching lets
    a test queue an AmbiguityReport plus several SqlGeneration responses without
    caring about call order.
    """

    def __init__(self, responses: Sequence[BaseModel]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []
        # self_consistency now issues concurrent calls, so guard the queue.
        self._lock = threading.Lock()

    def generate_structured(
        self,
        *,
        model: str,
        system: str,
        user: str,
        output_format: type[T],
        temperature: float,
    ) -> T:
        with self._lock:
            self.calls.append(
                {
                    "model": model,
                    "system": system,
                    "user": user,
                    "output_format": output_format,
                    "temperature": temperature,
                }
            )
            if not self._responses:
                raise AssertionError("FakeLLMClient ran out of queued responses.")
            for i, response in enumerate(self._responses):
                if isinstance(response, output_format):
                    return cast(T, self._responses.pop(i))
            return cast(T, self._responses.pop(0))


def build_fixture_db(path: str) -> None:
    """Create a tiny Olist-shaped DB: products and order_items with an FK."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE products (product_id TEXT PRIMARY KEY, product_category_name TEXT)")
    conn.execute(
        "CREATE TABLE order_items ("
        "order_id TEXT NOT NULL, order_item_id INTEGER NOT NULL, "
        "product_id TEXT REFERENCES products(product_id), "
        "price REAL NOT NULL, freight_value REAL NOT NULL, "
        "PRIMARY KEY (order_id, order_item_id))"
    )
    conn.executemany(
        "INSERT INTO products VALUES (?, ?)",
        [("p1", "toys"), ("p2", "books"), ("p3", "toys")],
    )
    conn.executemany(
        "INSERT INTO order_items VALUES (?, ?, ?, ?, ?)",
        [
            ("o1", 1, "p1", 30.0, 5.0),
            ("o2", 1, "p2", 10.0, 2.0),
            ("o3", 1, "p3", 20.0, 3.0),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture
def fixture_db(tmp_path: Path) -> Iterator[str]:
    db_path = str(tmp_path / "fixture.db")
    build_fixture_db(db_path)
    yield db_path


@pytest.fixture
def test_settings(fixture_db: str) -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        demo_db_path=fixture_db,
        generation_model="claude-sonnet-4-6",
        sql_default_limit=500,
        sql_timeout_seconds=10.0,
        max_self_correction_attempts=2,
        self_consistency_samples=3,
        self_consistency_temperature=0.7,
        # Point at a path that never exists so tests stay deterministic regardless of
        # whether a real eval/out/calibration.json has been committed.
        calibration_path="backend/tests/_no_such_calibration.json",
        cors_origins=("http://localhost:3000",),
        # Both <= 0 disables the /ask rate guard for deterministic endpoint tests.
        rate_limit_per_minute=0,
        daily_request_cap=0,
    )
