"""Endpoint tests for bring-your-own-data: /upload + session-scoped /ask and /schema."""

from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.llm import get_llm_client
from backend.app.main import app
from backend.app.pipeline.ambiguity import AmbiguityReport
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient

_CSV = b"city,orders\nSP,100\nRJ,50\n"
_SQL = "SELECT city, orders FROM data ORDER BY orders DESC"


def test_upload_csv_then_query_session(test_settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        client = TestClient(app)
        resp = client.post("/upload", files={"file": ("d.csv", _CSV, "text/csv")})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        session = body["session"]
        assert body["label"] == "csv"
        assert {t["name"] for t in body["tables"]} == {"data"}

        schema = client.get(f"/schema?session={session}").json()
        assert schema["dataset"] == "custom"
        assert any(t["name"] == "data" for t in schema["tables"])

        responses: list[BaseModel] = [AmbiguityReport(needs_clarification=False)]
        responses += [SqlGeneration(sql=_SQL, explanation="orders by city") for _ in range(3)]
        app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(responses)
        ask = client.post("/ask", json={"question": "orders by city", "session": session})
        assert ask.status_code == 200, ask.text
        answer = ask.json()
        assert answer["kind"] == "answer"
        assert answer["answer"]["row_count"] == 2
        # Custom datasets run uncalibrated (the map was fit on Olist).
        assert answer["confidence"]["calibrated"] is False
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_bad_csv(test_settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        client = TestClient(app)
        resp = client.post("/upload", files={"file": ("empty.csv", b"only_header\n", "text/csv")})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_ask_with_unknown_session_is_404(test_settings: Settings) -> None:
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient([])
    try:
        client = TestClient(app)
        resp = client.post("/ask", json={"question": "x", "session": "does-not-exist"})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
