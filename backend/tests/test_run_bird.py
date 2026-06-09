"""Tests for the BIRD runner core (mocked LLM, fixture DB, no API)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.pipeline.ambiguity import AmbiguityReport
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient
from eval import run_bird

_GOLD = "SELECT product_id FROM products ORDER BY product_id"
_WRONG = "SELECT product_id FROM products WHERE product_id = 'nope'"


@pytest.fixture
def eval_settings(test_settings: Settings, tmp_path: Path) -> Settings:
    # Point calibration at a missing file so confidence uses the identity placeholder.
    return dataclasses.replace(test_settings, calibration_path=str(tmp_path / "none.json"))


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch: pytest.MonkeyPatch, fixture_db: str) -> None:
    monkeypatch.setattr(run_bird, "bird_db_path", lambda db_id: Path(fixture_db))


def _question() -> dict[str, object]:
    return {
        "question_id": 1,
        "db_id": "fix",
        "difficulty": "simple",
        "question": "list product ids",
        "evidence": "",
        "SQL": _GOLD,
    }


def test_correct_when_prediction_matches_gold(eval_settings: Settings) -> None:
    responses: list[BaseModel] = [AmbiguityReport(needs_clarification=False)]
    responses += [SqlGeneration(sql=_GOLD, explanation="x") for _ in range(4)]
    rec = run_bird.evaluate_question(
        _question(),
        client=FakeLLMClient(responses),
        model="claude-haiku-4-5",
        settings=eval_settings,
    )
    assert rec["clarified"] is False
    assert rec["executed_ok"] is True
    assert rec["correct"] is True
    assert rec["baseline_correct"] is True
    assert rec["confidence_score"] is not None


def test_semantic_error_when_prediction_wrong(eval_settings: Settings) -> None:
    responses: list[BaseModel] = [AmbiguityReport(needs_clarification=False)]
    responses += [SqlGeneration(sql=_WRONG, explanation="x") for _ in range(4)]
    rec = run_bird.evaluate_question(
        _question(),
        client=FakeLLMClient(responses),
        model="claude-haiku-4-5",
        settings=eval_settings,
    )
    assert rec["executed_ok"] is True  # ran fine
    assert rec["correct"] is False  # wrong result -> semantic error
    assert rec["error_class"] == "none"


def test_clarified_skips_answer_but_runs_baseline(eval_settings: Settings) -> None:
    responses: list[BaseModel] = [
        AmbiguityReport(needs_clarification=True, dimensions=["metric"]),
        SqlGeneration(sql=_GOLD, explanation="baseline"),
    ]
    rec = run_bird.evaluate_question(
        _question(),
        client=FakeLLMClient(responses),
        model="claude-haiku-4-5",
        settings=eval_settings,
    )
    assert rec["clarified"] is True
    assert rec["executed_ok"] is False
    assert rec["confidence_score"] is None
    assert rec["baseline_correct"] is True  # baseline still answers


def test_run_subset_processes_all(eval_settings: Settings) -> None:
    # Two questions; queue enough matched responses for both (type-aware fake).
    responses: list[BaseModel] = []
    for _ in range(2):
        responses.append(AmbiguityReport(needs_clarification=False))
        responses += [SqlGeneration(sql=_GOLD, explanation="x") for _ in range(4)]
    q1 = _question()
    q2 = {**_question(), "question_id": 2}
    records = run_bird.run_subset(
        [q1, q2], client=FakeLLMClient(responses), model="claude-haiku-4-5", settings=eval_settings
    )
    assert len(records) == 2
    assert all(r["correct"] for r in records)
