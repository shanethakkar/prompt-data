"""Confidence via self-consistency.

The displayed answer is the deterministic (temperature 0) generation. Confidence
comes from sampling K-1 additional generations at nonzero temperature, executing
each, and measuring how many produce the same result set as the primary. That
agreement fraction, lightly penalized when self-correction fired, forms a raw
score, which a calibration map then maps to a displayed confidence.

The calibration map is fit offline by eval/calibrate.py (Phase 3) and loaded
statically here; nothing is fit at request time. Until that map exists, the
placeholder is the identity and confidence is flagged uncalibrated. canonicalize_rows
is shared with eval/metrics.py in Phase 3.
"""

from __future__ import annotations

import bisect
import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any

from backend.app.config import Settings
from backend.app.llm import LLMClient
from backend.app.pipeline.execute import ExecutionResult, ValidationError, execute_query
from backend.app.pipeline.generate import generate_sql

CanonicalResult = tuple[tuple[Any, ...], ...]


@dataclass
class Confidence:
    """Confidence signal attached to an answer."""

    score: float
    raw: float
    agreement: float
    samples: int
    self_correction_fired: bool
    calibrated: bool
    explanation: str


@dataclass
class CalibrationMap:
    """Monotonic map from raw confidence to calibrated confidence.

    Placeholder (calibrated=False) is the identity. A real map (Phase 3) carries
    sorted (xs, ys) control points and is applied by linear interpolation, so the
    server needs no numpy/scipy at request time.
    """

    calibrated: bool
    xs: list[float]
    ys: list[float]

    def apply(self, raw: float) -> float:
        if not self.calibrated or not self.xs:
            return raw
        if raw <= self.xs[0]:
            return self.ys[0]
        if raw >= self.xs[-1]:
            return self.ys[-1]
        i = bisect.bisect_right(self.xs, raw)
        x0, x1 = self.xs[i - 1], self.xs[i]
        y0, y1 = self.ys[i - 1], self.ys[i]
        if x1 == x0:
            return y0
        return y0 + (y1 - y0) * (raw - x0) / (x1 - x0)


def _normalize_cell(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def canonicalize_rows(columns: list[str], rows: list[tuple[Any, ...]]) -> CanonicalResult:
    """Order-insensitive, float-rounded canonical form of a result set.

    Compares values positionally; column names/aliases are ignored. Rows are
    sorted by repr to avoid cross-type comparison errors and to be deterministic.
    """
    _ = columns
    normalized = [tuple(_normalize_cell(c) for c in row) for row in rows]
    return tuple(sorted(normalized, key=repr))


def self_consistency(
    question: str,
    *,
    client: LLMClient,
    model: str,
    db_path: str,
    schema_context: str,
    semantic_context: str,
    settings: Settings,
    primary_execution: ExecutionResult,
) -> tuple[float, int]:
    """Sample K-1 extra generations at nonzero temperature; return (agreement, K).

    The primary counts as one of the K votes. Samples that fail validation,
    error, or time out count as non-matching.
    """
    k = max(1, settings.self_consistency_samples)
    if k == 1:
        return 1.0, 1

    target = canonicalize_rows(primary_execution.columns, primary_execution.rows)
    matches = 1  # the primary itself
    for _ in range(k - 1):
        sample = generate_sql(
            question,
            client=client,
            model=model,
            schema_context=schema_context,
            semantic_context=semantic_context,
            temperature=settings.self_consistency_temperature,
        )
        try:
            execution = execute_query(
                sample.sql,
                db_path,
                default_limit=settings.sql_default_limit,
                timeout_seconds=settings.sql_timeout_seconds,
            )
        except (ValidationError, sqlite3.Error):
            continue
        if execution.timed_out:
            continue
        if canonicalize_rows(execution.columns, execution.rows) == target:
            matches += 1

    return matches / k, k


def load_calibration_map(path: str) -> CalibrationMap:
    """Load the static calibration map, or the identity placeholder if absent.

    Real map format (Phase 3): {"type": "isotonic", "x": [...], "y": [...]}.
    Anything else (missing file, {"type": "identity"}) yields the uncalibrated identity.
    """
    if not os.path.exists(path):
        return CalibrationMap(calibrated=False, xs=[], ys=[])
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return CalibrationMap(calibrated=False, xs=[], ys=[])
    if data.get("type") == "isotonic" and data.get("x") and data.get("y"):
        return CalibrationMap(calibrated=True, xs=list(data["x"]), ys=list(data["y"]))
    return CalibrationMap(calibrated=False, xs=[], ys=[])


def compute_confidence(
    *,
    agreement: float,
    samples: int,
    self_correction_fired: bool,
    retrieval_score: float,
    calibration: CalibrationMap,
) -> Confidence:
    """Combine the signals into a raw score and apply the calibration map."""
    penalty = 0.85 if self_correction_fired else 1.0
    raw = max(0.0, min(1.0, agreement * penalty * retrieval_score))
    score = calibration.apply(raw)

    explanation = f"{round(agreement * 100)}% agreement across {samples} samples"
    if self_correction_fired:
        explanation += "; self-correction fired"
    if not calibration.calibrated:
        explanation += "; provisional (not yet calibrated)"

    return Confidence(
        score=score,
        raw=raw,
        agreement=agreement,
        samples=samples,
        self_correction_fired=self_correction_fired,
        calibrated=calibration.calibrated,
        explanation=explanation,
    )
