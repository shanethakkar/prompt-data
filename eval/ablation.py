"""Trust-layer ablation: the confidently-wrong reduction.

Compares the confidently-wrong rate with the trust layer (clarify + calibrated
confidence gating) against the baseline pipeline that just answers. The reduction
is the project's signature number.
"""

from __future__ import annotations

from dataclasses import dataclass

from eval.metrics import (
    CONFIDENT_THRESHOLD,
    EvalRecord,
    baseline_confidently_wrong_rate,
    confidently_wrong_rate,
)


@dataclass
class Ablation:
    threshold: float
    baseline_confidently_wrong: float
    trust_confidently_wrong: float
    absolute_reduction: float
    relative_reduction: float  # fraction of baseline confidently-wrong removed


def compute_ablation(records: list[EvalRecord], threshold: float = CONFIDENT_THRESHOLD) -> Ablation:
    baseline = baseline_confidently_wrong_rate(records)
    trust = confidently_wrong_rate(records, threshold)
    absolute = baseline - trust
    relative = absolute / baseline if baseline > 0 else 0.0
    return Ablation(
        threshold=threshold,
        baseline_confidently_wrong=baseline,
        trust_confidently_wrong=trust,
        absolute_reduction=absolute,
        relative_reduction=relative,
    )
