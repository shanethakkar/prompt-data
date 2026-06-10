"""Tests for the orchestrator and the /ask endpoint (mocked LLM)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.llm import get_llm_client
from backend.app.main import app
from backend.app.pipeline.ambiguity import AmbiguityReport
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
    assert suggest_chart(["order_month", "orders"], [("2017-01", 10), ("2017-02", 14)]) == "line"
    # A month/year/date column name keeps the line even when values are bare numbers.
    assert suggest_chart(["month", "orders"], [("01", 10), ("02", 14), ("03", 9)]) == "line"
    # Full dates and calendar years are also time series.
    assert suggest_chart(["d", "n"], [("2017-03-15", 3), ("2017-03-16", 5)]) == "line"
    assert suggest_chart(["year", "orders"], [(2016, 9), (2017, 11), (2018, 13)]) == "line"


def test_suggest_chart_bar_for_categorical_time_like_names() -> None:
    # "day of week" reads like time but is categorical -> bar, not line.
    assert suggest_chart(["day_of_week", "orders"], [("Monday", 120), ("Tuesday", 98)]) == "bar"
    assert suggest_chart(["day_of_week", "avg_orders"], [(0, 120), (1, 98), (2, 105)]) == "bar"
    assert suggest_chart(["payment_type", "n"], [("credit_card", 50), ("boleto", 20)]) == "bar"


def test_suggest_chart_charts_with_helper_column() -> None:
    # A sort/helper column (day_num) between the label and the metric still charts: x = label,
    # value = rightmost numeric column (avg_price).
    rows = [("Sunday", 0, 133.7), ("Monday", 1, 138.8), ("Tuesday", 2, 137.2)]
    assert suggest_chart(["day_of_week", "day_num", "avg_price"], rows) == "bar"
    rows_m = [("2017-01", 1, 800), ("2017-02", 2, 1780)]
    assert suggest_chart(["month", "month_num", "orders"], rows_m) == "line"
    # Up to four columns of numeric helpers/measures still charts the rightmost value.
    assert suggest_chart(["day", "day_num", "n", "avg"], [("Mon", 1, 9, 5.0)]) == "bar"


def test_suggest_chart_table_for_wide() -> None:
    # Five+ columns is a genuine multi-metric table.
    assert suggest_chart(["a", "b", "c", "d", "e"], [(1, 2, 3, 4, 5)]) == "table"
    # No numeric measure after the label -> table.
    assert suggest_chart(["category", "label"], [("toys", "x"), ("books", "y")]) == "table"
    # A second categorical dimension (region) before the value -> table, not a collapsed bar.
    assert suggest_chart(["category", "region", "revenue"], [("toys", "south", 50.0)]) == "table"


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
# /ask endpoint (TrustedResponse shape)                                       #
# --------------------------------------------------------------------------- #


def _post(
    client: FakeLLMClient, test_settings: Settings, payload: dict[str, object]
) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_llm_client] = lambda: client
    app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        resp = TestClient(app).post("/ask", json=payload)
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    return body


def test_ask_endpoint_answer(test_settings: Settings) -> None:
    responses: list[BaseModel] = [AmbiguityReport(needs_clarification=False)]
    responses += [
        SqlGeneration(sql=_REVENUE_SQL, explanation="Revenue by category.") for _ in range(3)
    ]
    body = _post(FakeLLMClient(responses), test_settings, {"question": "revenue by category"})

    assert body["kind"] == "answer"
    assert body["answer"]["chart_type"] == "bar"
    assert body["answer"]["row_count"] == 2
    assert body["answer"]["rows"][0] == ["toys", 50.0]  # rows are lists in JSON, highest first
    assert body["assumptions"]["tables"] == ["order_items", "products"]
    assert body["confidence"]["calibrated"] is False


def test_ask_endpoint_clarification(test_settings: Settings) -> None:
    client = FakeLLMClient(
        [
            AmbiguityReport(
                needs_clarification=True,
                dimensions=["time_window"],
                clarifying_question="Which time window?",
                options=["last 30 days", "all time"],
            )
        ]
    )
    body = _post(client, test_settings, {"question": "recent top products"})
    assert body["kind"] == "clarification"
    assert body["clarification"]["options"] == ["last 30 days", "all time"]
    assert body["answer"] is None
