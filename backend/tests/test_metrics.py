"""Tests for the pure eval metric functions."""

from __future__ import annotations

from eval.metrics import (
    EvalRecord,
    LabeledResult,
    baseline_confidently_wrong_rate,
    brier_score,
    clarification_precision_recall,
    confidently_wrong_rate,
    execution_accuracy,
    expected_calibration_error,
    reliability_bins,
    semantic_error_rate,
)


def _record(**overrides: object) -> EvalRecord:
    base: EvalRecord = {
        "question_id": 0,
        "db_id": "db",
        "difficulty": "simple",
        "clarified": False,
        "executed_ok": True,
        "correct": True,
        "error_class": "none",
        "confidence_raw": 0.9,
        "confidence_score": 0.9,
        "agreement": 0.9,
        "self_correction_fired": False,
        "predicted_sql": "SELECT 1",
        "baseline_executed_ok": True,
        "baseline_correct": True,
        "latency_ms": 1.0,
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def test_execution_accuracy() -> None:
    recs = [_record(correct=True), _record(correct=False), _record(clarified=True, correct=False)]
    assert execution_accuracy(recs) == 1 / 3


def test_semantic_error_rate_counts_answered_wrong_only() -> None:
    recs = [
        _record(correct=False, executed_ok=True),  # semantic error
        _record(clarified=True, executed_ok=False, correct=False),  # clarified, not an error
        _record(correct=True),  # correct
    ]
    assert semantic_error_rate(recs) == 1 / 3


def test_confidently_wrong_vs_baseline() -> None:
    recs = [
        # answered, wrong, high confidence -> confidently wrong (with trust)
        _record(correct=False, confidence_score=0.9, baseline_correct=False),
        # answered, wrong, LOW confidence -> not confidently wrong with trust, but is baseline-wrong
        _record(correct=False, confidence_score=0.3, baseline_correct=False),
        # clarified -> neither
        _record(clarified=True, correct=False, confidence_score=None, baseline_correct=True),
    ]
    assert confidently_wrong_rate(recs) == 1 / 3
    assert baseline_confidently_wrong_rate(recs) == 2 / 3  # both baseline-wrong rows


def test_brier_and_ece() -> None:
    # Perfectly calibrated, confident-correct predictions -> ~0 error.
    confs = [1.0, 1.0, 0.0]
    correct = [True, True, False]
    assert brier_score(confs, correct) == 0.0
    assert expected_calibration_error(confs, correct) == 0.0


def test_reliability_bins_group_by_confidence() -> None:
    bins = reliability_bins([0.95, 0.05], [True, False], bins=10)
    top = bins[-1]
    assert top.count == 1 and top.observed == 1.0
    bottom = bins[0]
    assert bottom.count == 1 and bottom.observed == 0.0


def test_clarification_precision_recall() -> None:
    labeled: list[LabeledResult] = [
        {"ambiguous": True, "flagged": True},  # TP
        {"ambiguous": True, "flagged": False},  # FN
        {"ambiguous": False, "flagged": True},  # FP (over-ask)
        {"ambiguous": False, "flagged": False},  # TN
    ]
    s = clarification_precision_recall(labeled)
    assert s.precision == 0.5
    assert s.recall == 0.5
    assert s.over_ask_rate == 0.5
