"""Tests for the trap eval: metrics and the runner (mocked LLM, fixture DB)."""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.pipeline.ambiguity import AmbiguityReport
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient
from eval import run_traps
from eval.metrics import TrapRecord, trap_scores

_GOOD = "SELECT product_id FROM products ORDER BY product_id"


# --------------------------------------------------------------------------- #
# trap_scores (pure)                                                          #
# --------------------------------------------------------------------------- #


def _trap(**o: object) -> TrapRecord:
    base: TrapRecord = {
        "id": "x",
        "category": "unanswerable",
        "should_decline": True,
        "trust_outcome": "clarified",
        "trust_confidence": None,
        "baseline_outcome": "answered",
    }
    base.update(o)  # type: ignore[typeddict-item]
    return base


def test_trap_scores_reduction_and_over_decline() -> None:
    records = [
        # traps: baseline answers all 3; trust clarifies 2, answers 1
        _trap(should_decline=True, baseline_outcome="answered", trust_outcome="clarified"),
        _trap(should_decline=True, baseline_outcome="answered", trust_outcome="failed"),
        _trap(should_decline=True, baseline_outcome="answered", trust_outcome="answered"),
        # clear controls: trust answers both (no over-decline)
        _trap(
            should_decline=False,
            category="clear",
            baseline_outcome="answered",
            trust_outcome="answered",
        ),
        _trap(
            should_decline=False,
            category="clear",
            baseline_outcome="answered",
            trust_outcome="answered",
        ),
    ]
    s = trap_scores(records)
    assert s.n_traps == 3 and s.n_clear == 2
    assert s.baseline_confidently_answered == 1.0  # baseline answered all traps
    assert s.trust_confidently_answered == pytest.approx(1 / 3)  # trust answered 1 of 3
    assert s.absolute_reduction == pytest.approx(2 / 3)
    assert s.over_decline_rate == 0.0


def test_trap_scores_detects_over_decline() -> None:
    records = [
        _trap(
            should_decline=False,
            category="clear",
            trust_outcome="clarified",
            baseline_outcome="answered",
        ),
        _trap(
            should_decline=False,
            category="clear",
            trust_outcome="answered",
            baseline_outcome="answered",
        ),
    ]
    assert trap_scores(records).over_decline_rate == 0.5


# --------------------------------------------------------------------------- #
# evaluate_trap (mocked LLM + fixture DB)                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture
def trap_settings(test_settings: Settings, fixture_db: str) -> Settings:
    return dataclasses.replace(test_settings, demo_db_path=fixture_db)


def test_evaluate_trap_clarified(trap_settings: Settings) -> None:
    # Ambiguity gate flags it -> trust clarifies; baseline still answers.
    responses: list[BaseModel] = [
        AmbiguityReport(needs_clarification=True, dimensions=["metric"]),
        SqlGeneration(sql=_GOOD, explanation="baseline"),
    ]
    rec = run_traps.evaluate_trap(
        {"id": "t1", "category": "ambiguous_metric", "question": "top sellers?", "ambiguous": True},
        client=FakeLLMClient(responses),
        model="claude-sonnet-4-6",
        settings=trap_settings,
    )
    assert rec["trust_outcome"] == "clarified"
    assert rec["baseline_outcome"] == "answered"


def test_evaluate_trap_answered(trap_settings: Settings) -> None:
    # Gate passes -> trust answers (slip-through); K=3 -> primary + 2 samples + baseline.
    responses: list[BaseModel] = [AmbiguityReport(needs_clarification=False)]
    responses += [SqlGeneration(sql=_GOOD, explanation="x") for _ in range(4)]
    rec = run_traps.evaluate_trap(
        {"id": "t2", "category": "unanswerable", "question": "customer emails?", "ambiguous": True},
        client=FakeLLMClient(responses),
        model="claude-sonnet-4-6",
        settings=trap_settings,
    )
    assert rec["trust_outcome"] == "answered"
    assert rec["trust_confidence"] is not None
    assert rec["baseline_outcome"] == "answered"
