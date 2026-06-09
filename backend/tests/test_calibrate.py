"""Tests for the PAVA isotonic calibration fit."""

from __future__ import annotations

from pathlib import Path

from backend.app.pipeline.confidence import load_calibration_map
from eval.calibrate import isotonic_fit, write_calibration_map


def test_fit_is_monotonic_nondecreasing() -> None:
    # Correctness rises with confidence, with one inversion PAVA must smooth.
    raw = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    correct = [False, False, True, False, True, True, True, True, True]
    xs, ys = isotonic_fit(raw, correct)
    assert len(xs) == len(ys) >= 2
    assert all(ys[i] <= ys[i + 1] + 1e-9 for i in range(len(ys) - 1))


def test_fit_improves_a_miscalibrated_set() -> None:
    # Low raw values that are actually all correct -> calibrated map should lift them.
    raw = [0.2, 0.25, 0.3, 0.35]
    correct = [True, True, True, True]
    xs, ys = isotonic_fit(raw, correct)
    assert ys[-1] >= ys[0]
    assert max(ys) >= 0.9  # pooled to ~1.0 since all correct


def test_written_map_round_trips_through_server_loader(tmp_path: Path) -> None:
    raw = [0.1, 0.4, 0.6, 0.9]
    correct = [False, False, True, True]
    xs, ys = isotonic_fit(raw, correct)
    path = str(tmp_path / "calibration.json")
    assert write_calibration_map(path, xs, ys) is True

    cmap = load_calibration_map(path)
    assert cmap.calibrated is True
    # Applying within range returns a value bounded by the fitted endpoints.
    val = cmap.apply(0.5)
    assert min(ys) <= val <= max(ys)


def test_insufficient_data_writes_identity(tmp_path: Path) -> None:
    xs, ys = isotonic_fit([0.5], [True])
    assert xs == [] and ys == []
    path = str(tmp_path / "calibration.json")
    assert write_calibration_map(path, xs, ys) is False
    assert load_calibration_map(path).calibrated is False
