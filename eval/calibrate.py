"""Calibration map fitting (pure-Python isotonic regression via PAVA).

Fits a monotonic non-decreasing map from raw confidence to observed accuracy on a
held-out train split, then writes eval/out/calibration.json in the format
confidence.load_calibration_map reads. No numpy/scipy, so the eval stays light and
the server never needs them either.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.pipeline.confidence import CalibrationMap


def _pava(values: list[float], weights: list[float]) -> list[float]:
    """Pool adjacent violators: nearest non-decreasing fit (least squares)."""
    block_sum: list[float] = []
    block_w: list[float] = []
    block_len: list[int] = []
    for v, w in zip(values, weights, strict=True):
        block_sum.append(v * w)
        block_w.append(w)
        block_len.append(1)
        while len(block_sum) > 1 and block_sum[-2] / block_w[-2] > block_sum[-1] / block_w[-1]:
            s = block_sum.pop()
            wt = block_w.pop()
            ln = block_len.pop()
            block_sum[-1] += s
            block_w[-1] += wt
            block_len[-1] += ln
    fitted: list[float] = []
    for s, wt, ln in zip(block_sum, block_w, block_len, strict=True):
        fitted.extend([s / wt] * ln)
    return fitted


def isotonic_fit(raw: list[float], correct: list[bool]) -> tuple[list[float], list[float]]:
    """Fit raw confidence -> calibrated probability. Returns sorted (xs, ys) control points."""
    if len(raw) < 2:
        return [], []
    pairs = sorted(zip(raw, [1.0 if c else 0.0 for c in correct], strict=True), key=lambda p: p[0])
    xs_sorted = [p[0] for p in pairs]
    ys_target = [p[1] for p in pairs]
    fitted = _pava(ys_target, [1.0] * len(ys_target))

    # Collapse duplicate x values, keeping the last (largest, since non-decreasing).
    dedup: dict[float, float] = {}
    for x, y in zip(xs_sorted, fitted, strict=True):
        dedup[x] = y
    xs = sorted(dedup)
    ys = [dedup[x] for x in xs]
    return xs, ys


def build_map(xs: list[float], ys: list[float]) -> CalibrationMap:
    """Wrap fitted points in the CalibrationMap the server uses (calibrated if non-trivial)."""
    return CalibrationMap(calibrated=len(xs) >= 2, xs=xs, ys=ys)


def write_calibration_map(path: str, xs: list[float], ys: list[float]) -> bool:
    """Write the isotonic map JSON. Returns True if a real map was written."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if len(xs) >= 2:
        payload = {"type": "isotonic", "x": xs, "y": ys}
    else:
        payload = {"type": "identity"}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(xs) >= 2
