"""Evaluation metrics (pure functions over per-question records).

No API, no I/O. The runner produces EvalRecords; these functions turn them into
the headline numbers. Result-set equality is decided upstream in the runner via
confidence.canonicalize_rows; here records already carry the boolean outcomes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict


class EvalRecord(TypedDict):
    """One BIRD question's outcome under both the trust and baseline pipelines."""

    question_id: int
    db_id: str
    difficulty: str
    clarified: bool
    executed_ok: bool
    correct: bool
    error_class: str  # none | validation | sqlite | timeout | no_answer
    confidence_raw: float | None
    confidence_score: float | None
    agreement: float | None
    self_correction_fired: bool
    predicted_sql: str
    baseline_executed_ok: bool
    baseline_correct: bool
    latency_ms: float


CONFIDENT_THRESHOLD = 0.8


def execution_accuracy(records: list[EvalRecord]) -> float:
    """Fraction of all questions answered correctly (clarified counts as not correct)."""
    if not records:
        return 0.0
    return sum(1 for r in records if r["correct"]) / len(records)


def answered_accuracy(records: list[EvalRecord]) -> float:
    """Accuracy among questions the trust layer chose to answer (not clarified)."""
    answered = [r for r in records if not r["clarified"]]
    if not answered:
        return 0.0
    return sum(1 for r in answered if r["correct"]) / len(answered)


def clarification_rate(records: list[EvalRecord]) -> float:
    if not records:
        return 0.0
    return sum(1 for r in records if r["clarified"]) / len(records)


def semantic_error_rate(records: list[EvalRecord]) -> float:
    """Answered, executed without error, but returned the wrong result. Headline metric."""
    if not records:
        return 0.0
    errors = sum(1 for r in records if not r["clarified"] and r["executed_ok"] and not r["correct"])
    return errors / len(records)


def confidently_wrong_rate(
    records: list[EvalRecord], threshold: float = CONFIDENT_THRESHOLD
) -> float:
    """With the trust layer: answered, wrong, and still confident at/above the threshold."""
    if not records:
        return 0.0
    n = sum(
        1
        for r in records
        if not r["clarified"]
        and r["executed_ok"]
        and not r["correct"]
        and r["confidence_score"] is not None
        and r["confidence_score"] >= threshold
    )
    return n / len(records)


def baseline_confidently_wrong_rate(records: list[EvalRecord]) -> float:
    """Without the trust layer: every executed-but-wrong answer is emitted confidently."""
    if not records:
        return 0.0
    n = sum(1 for r in records if r["baseline_executed_ok"] and not r["baseline_correct"])
    return n / len(records)


# --------------------------------------------------------------------------- #
# Calibration                                                                 #
# --------------------------------------------------------------------------- #


def brier_score(confidences: list[float], correct: list[bool]) -> float:
    if not confidences:
        return 0.0
    return sum(
        (c - (1.0 if y else 0.0)) ** 2 for c, y in zip(confidences, correct, strict=True)
    ) / len(confidences)


@dataclass
class ReliabilityBin:
    lower: float
    upper: float
    predicted: float  # mean confidence in the bin
    observed: float  # observed accuracy in the bin
    count: int


def reliability_bins(
    confidences: list[float], correct: list[bool], bins: int = 10
) -> list[ReliabilityBin]:
    """Bin predictions by confidence; report mean confidence vs observed accuracy."""
    out: list[ReliabilityBin] = []
    for b in range(bins):
        lo = b / bins
        hi = (b + 1) / bins
        # Last bin is inclusive of 1.0.
        members = [
            (c, y)
            for c, y in zip(confidences, correct, strict=True)
            if (lo <= c < hi) or (b == bins - 1 and c == 1.0)
        ]
        if not members:
            out.append(ReliabilityBin(lo, hi, 0.0, 0.0, 0))
            continue
        pred = sum(c for c, _ in members) / len(members)
        obs = sum(1 for _, y in members if y) / len(members)
        out.append(ReliabilityBin(lo, hi, pred, obs, len(members)))
    return out


def expected_calibration_error(
    confidences: list[float], correct: list[bool], bins: int = 10
) -> float:
    """ECE: weighted average gap between confidence and accuracy across bins."""
    if not confidences:
        return 0.0
    total = len(confidences)
    ece = 0.0
    for rb in reliability_bins(confidences, correct, bins):
        if rb.count:
            ece += (rb.count / total) * abs(rb.predicted - rb.observed)
    return ece


# --------------------------------------------------------------------------- #
# Clarification precision / recall                                            #
# --------------------------------------------------------------------------- #


class LabeledResult(TypedDict):
    ambiguous: bool  # ground truth
    flagged: bool  # model raised a clarification


@dataclass
class ClarificationScores:
    precision: float
    recall: float
    over_ask_rate: float  # fraction of clear questions wrongly clarified
    true_positive: int
    false_positive: int
    false_negative: int


class TrapRecord(TypedDict):
    """Outcome of a trap question (one that should NOT be confidently answered)."""

    id: str
    category: str
    should_decline: bool  # True for traps, False for clear controls
    trust_outcome: str  # clarified | failed | answered
    trust_confidence: float | None  # calibrated confidence when answered
    baseline_outcome: str  # failed | answered


@dataclass
class TrapScores:
    n_traps: int
    n_clear: int
    baseline_confidently_answered: float  # on should-decline questions
    trust_confidently_answered: float  # on should-decline questions
    absolute_reduction: float
    relative_reduction: float
    over_decline_rate: float  # clear controls the trust layer did NOT answer
    by_category: dict[str, float]  # trust confidently-answered rate per trap category


def trap_scores(records: list[TrapRecord]) -> TrapScores:
    """Confidently-wrong reduction on should-decline questions, plus over-decline on clear.

    'Confidently answered' = produced an executable answer (no clarify, no execution failure)
    to a question that should have been declined or clarified. Threshold-free: the headline is
    whether the trust layer answered at all, since clarification is the primary defense.
    """
    traps = [r for r in records if r["should_decline"]]
    clear = [r for r in records if not r["should_decline"]]

    def answered_rate(rows: list[TrapRecord], get: Callable[[TrapRecord], str]) -> float:
        if not rows:
            return 0.0
        return sum(1 for r in rows if get(r) == "answered") / len(rows)

    baseline = answered_rate(traps, lambda r: r["baseline_outcome"])
    trust = answered_rate(traps, lambda r: r["trust_outcome"])
    over_decline = (
        sum(1 for r in clear if r["trust_outcome"] != "answered") / len(clear) if clear else 0.0
    )

    by_category: dict[str, float] = {}
    for cat in sorted({r["category"] for r in traps}):
        rows = [r for r in traps if r["category"] == cat]
        by_category[cat] = answered_rate(rows, lambda r: r["trust_outcome"])

    return TrapScores(
        n_traps=len(traps),
        n_clear=len(clear),
        baseline_confidently_answered=baseline,
        trust_confidently_answered=trust,
        absolute_reduction=baseline - trust,
        relative_reduction=(baseline - trust) / baseline if baseline > 0 else 0.0,
        over_decline_rate=over_decline,
        by_category=by_category,
    )


def clarification_precision_recall(labeled: list[LabeledResult]) -> ClarificationScores:
    tp = sum(1 for x in labeled if x["flagged"] and x["ambiguous"])
    fp = sum(1 for x in labeled if x["flagged"] and not x["ambiguous"])
    fn = sum(1 for x in labeled if not x["flagged"] and x["ambiguous"])
    clear = sum(1 for x in labeled if not x["ambiguous"])
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    over_ask = fp / clear if clear else 0.0
    return ClarificationScores(precision, recall, over_ask, tp, fp, fn)
