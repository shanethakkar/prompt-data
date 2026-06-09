"""Tests for the orchestrator and the /ask endpoint (mocked LLM)."""

from __future__ import annotations

from backend.app.config import Settings, get_settings
from backend.app.llm import get_llm_client
from backend.app.main import app
from backend.app.pipeline.answer import answer_question, suggest_chart
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient

_REVENUE_SQL = (
    "SELECT product_category_name, SUM(price) AS revenue "
    "FROM order_items JOIN products USING (product_id) "
    "GROUP BY product_category_name ORDER BY revenue DESC"
)


# --------------------------------------------------------------------------- #
# suggest_chart heuristic                                                     #
# --------------------------------------------------------------------------- #


def test_suggest_chart_none_for_empty() -> None:
    assert suggest_chart([], []) == "none"
    assert suggest_chart(["x"], []) == "none"


def test_suggest_chart_stat_for_single_cell() -> None:
    assert suggest_chart(["total"], [(42,)]) == "stat"


def test_suggest_chart_bar_for_category_numeric() -> None:
    assert suggest_chart(["category", "revenue"], [("toys", 50.0), ("books", 10.0)]) == "bar"


def test_suggest_chart_line_for_time_numeric() -> None:
    assert suggest_chart(["order_month", "orders"], [("2017-01", 10)]) == "line"


def test_suggest_chart_table_for_wide() -> None:
    assert suggest_chart(["a", "b", "c"], [(1, 2, 3)]) == "table"


# --------------------------------------------------------------------------- #
# answer_question orchestration                                               #
# --------------------------------------------------------------------------- #


def test_answer_question_end_to_end(test_settings: Settings) -> None:
    client = FakeLLMClient([SqlGeneration(sql=_REVENUE_SQL, explanation="Revenue by category.")])
    result = answer_question("revenue by category", client=client, settings=test_settings)

    assert result.error is None
    assert result.columns == ["product_category_name", "revenue"]
    assert result.row_count == 2  # toys and books
    assert result.chart_type == "bar"
    rows = dict(result.rows)
    assert rows["toys"] == 50.0  # 30 + 20
    assert rows["books"] == 10.0


def test_answer_question_reports_error_on_exhaustion(test_settings: Settings) -> None:
    client = FakeLLMClient(
        [SqlGeneration(sql="DROP TABLE products", explanation="bad") for _ in range(3)]
    )
    result = answer_question("drop it", client=client, settings=test_settings)
    assert result.error is not None
    assert result.row_count == 0
    assert result.chart_type == "none"


# --------------------------------------------------------------------------- #
# /ask endpoint                                                               #
# --------------------------------------------------------------------------- #


def test_ask_endpoint(test_settings: Settings) -> None:
    from fastapi.testclient import TestClient

    client = FakeLLMClient([SqlGeneration(sql=_REVENUE_SQL, explanation="Revenue by category.")])
    app.dependency_overrides[get_llm_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        resp = TestClient(app).post("/ask", json={"question": "revenue by category"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["chart_type"] == "bar"
    assert body["row_count"] == 2
    assert body["columns"] == ["product_category_name", "revenue"]
    assert body["error"] is None
