"""Tests for the SSE /ask/stream endpoint (mocked LLM)."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.llm import get_llm_client
from backend.app.main import app
from backend.app.pipeline.ambiguity import AmbiguityReport
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient

_REVENUE_SQL = (
    "SELECT product_category_name, SUM(price) AS revenue "
    "FROM order_items JOIN products USING (product_id) "
    "GROUP BY product_category_name ORDER BY revenue DESC"
)


def _events(
    client: FakeLLMClient, settings: Settings, payload: dict[str, object]
) -> list[dict[str, Any]]:
    app.dependency_overrides[get_llm_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        resp = TestClient(app).post("/ask/stream", json=payload)
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    out: list[dict[str, Any]] = []
    for line in resp.text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[len("data: ") :]))
    return out


def test_stream_answer_sequence(test_settings: Settings) -> None:
    responses: list[BaseModel] = [AmbiguityReport(needs_clarification=False)]
    responses += [SqlGeneration(sql=_REVENUE_SQL, explanation="revenue") for _ in range(3)]
    events = _events(FakeLLMClient(responses), test_settings, {"question": "revenue by category"})

    types = [e["type"] for e in events]
    assert types[0] == "stage" and events[0]["name"] == "ambiguity"
    assert "generating" in [e.get("name") for e in events if e["type"] == "stage"]

    # The answer streams before confidence (decoupled), and confidence is the terminal event.
    answer = next(e for e in events if e["type"] == "answer")
    confidence = next(e for e in events if e["type"] == "confidence")
    assert types.index("answer") < types.index("confidence")
    assert types[-1] == "confidence"
    assert answer["answer"]["row_count"] == 2
    assert answer["assumptions"]["tables"] == ["order_items", "products"]
    assert answer["confidence"] is None
    assert confidence["confidence"]["calibrated"] is False


def test_stream_clarification_sequence(test_settings: Settings) -> None:
    client = FakeLLMClient(
        [
            AmbiguityReport(
                needs_clarification=True,
                dimensions=["metric"],
                clarifying_question="By revenue or by count?",
                options=["by revenue", "by count"],
            )
        ]
    )
    events = _events(client, test_settings, {"question": "top products"})
    assert events[0]["type"] == "stage" and events[0]["name"] == "ambiguity"
    assert events[-1]["type"] == "clarification"
    assert events[-1]["clarification"]["options"] == ["by revenue", "by count"]
