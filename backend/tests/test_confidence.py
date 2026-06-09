"""Tests for self-consistency, canonicalization, and the calibration seam."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.config import Settings
from backend.app.pipeline.confidence import (
    canonicalize_rows,
    compute_confidence,
    load_calibration_map,
    self_consistency,
)
from backend.app.pipeline.execute import execute_query
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient

_REVENUE_SQL = (
    "SELECT product_category_name, SUM(price) AS revenue "
    "FROM order_items JOIN products USING (product_id) "
    "GROUP BY product_category_name ORDER BY revenue DESC"
)
_OTHER_SQL = "SELECT product_id FROM products ORDER BY product_id"


# --------------------------------------------------------------------------- #
# canonicalize_rows                                                           #
# --------------------------------------------------------------------------- #


def test_canonicalize_is_row_order_insensitive() -> None:
    a = canonicalize_rows(["x"], [(1,), (2,), (3,)])
    b = canonicalize_rows(["x"], [(3,), (1,), (2,)])
    assert a == b


def test_canonicalize_rounds_floats() -> None:
    a = canonicalize_rows(["x"], [(1.00000001,)])
    b = canonicalize_rows(["x"], [(1.0,)])
    assert a == b


def test_canonicalize_distinguishes_values() -> None:
    a = canonicalize_rows(["x"], [(1,)])
    b = canonicalize_rows(["x"], [(2,)])
    assert a != b


# --------------------------------------------------------------------------- #
# calibration map                                                             #
# --------------------------------------------------------------------------- #


def test_calibration_identity_when_absent(tmp_path: Path) -> None:
    cmap = load_calibration_map(str(tmp_path / "missing.json"))
    assert cmap.calibrated is False
    assert cmap.apply(0.42) == 0.42


def test_calibration_isotonic_interpolates(tmp_path: Path) -> None:
    p = tmp_path / "calibration.json"
    p.write_text(json.dumps({"type": "isotonic", "x": [0.0, 1.0], "y": [0.0, 0.5]}))
    cmap = load_calibration_map(str(p))
    assert cmap.calibrated is True
    assert cmap.apply(0.5) == 0.25  # midpoint of the 0->0, 1->0.5 line


# --------------------------------------------------------------------------- #
# compute_confidence                                                          #
# --------------------------------------------------------------------------- #


def test_confidence_penalizes_self_correction(tmp_path: Path) -> None:
    cmap = load_calibration_map(str(tmp_path / "missing.json"))
    clean = compute_confidence(
        agreement=1.0, samples=5, self_correction_fired=False, retrieval_score=1.0, calibration=cmap
    )
    corrected = compute_confidence(
        agreement=1.0, samples=5, self_correction_fired=True, retrieval_score=1.0, calibration=cmap
    )
    assert clean.raw == 1.0
    assert corrected.raw == 0.85
    assert clean.calibrated is False
    assert "provisional" in clean.explanation


# --------------------------------------------------------------------------- #
# self_consistency (mocked LLM + fixture DB)                                  #
# --------------------------------------------------------------------------- #


def test_full_agreement_when_samples_match(fixture_db: str, test_settings: Settings) -> None:
    primary = execute_query(_REVENUE_SQL, fixture_db)
    # samples = 3 -> 2 extra calls, both reproducing the primary result.
    client = FakeLLMClient([SqlGeneration(sql=_REVENUE_SQL, explanation="x") for _ in range(2)])
    agreement, k = self_consistency(
        "revenue by category",
        client=client,
        model="claude-sonnet-4-6",
        db_path=fixture_db,
        schema_context="s",
        semantic_context="l",
        settings=test_settings,
        primary_execution=primary,
    )
    assert k == 3
    assert agreement == 1.0


def test_partial_agreement_when_a_sample_differs(fixture_db: str, test_settings: Settings) -> None:
    primary = execute_query(_REVENUE_SQL, fixture_db)
    client = FakeLLMClient(
        [
            SqlGeneration(sql=_REVENUE_SQL, explanation="x"),
            SqlGeneration(sql=_OTHER_SQL, explanation="y"),
        ]
    )
    agreement, k = self_consistency(
        "revenue by category",
        client=client,
        model="claude-sonnet-4-6",
        db_path=fixture_db,
        schema_context="s",
        semantic_context="l",
        settings=test_settings,
        primary_execution=primary,
    )
    assert k == 3
    assert agreement == 2 / 3  # primary + 1 matching sample out of 3
