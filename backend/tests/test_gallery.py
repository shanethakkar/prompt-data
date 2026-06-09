"""Tests for the gallery capture core (mocked LLM, fixture DB)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.pipeline.ambiguity import AmbiguityReport
from backend.app.pipeline.generate import SqlGeneration
from backend.tests.conftest import FakeLLMClient
from eval import run_gallery

_GOOD = "SELECT product_id FROM products ORDER BY product_id"


@pytest.fixture
def gallery_settings(test_settings: Settings, fixture_db: str) -> Settings:
    return dataclasses.replace(
        test_settings, demo_db_path=fixture_db, calibration_path=str(Path("nope.json"))
    )


def _item() -> dict[str, str]:
    return {"id": "x", "category": "Test", "question": "list products", "takeaway": "t"}


def test_capture_card_answered(gallery_settings: Settings) -> None:
    # 1 naive generation + ambiguity(clear) + primary + 2 self-consistency samples.
    responses: list[BaseModel] = [SqlGeneration(sql=_GOOD, explanation="naive")]
    responses += [AmbiguityReport(needs_clarification=False)]
    responses += [SqlGeneration(sql=_GOOD, explanation="verity") for _ in range(3)]
    card = run_gallery.capture_card(
        _item(),
        client=FakeLLMClient(responses),
        model="claude-sonnet-4-6",
        settings=gallery_settings,
    )
    assert card["naive"]["sql"] == _GOOD
    assert card["naive"]["row_count"] == 3
    assert card["verity"]["kind"] == "answer"
    assert card["verity"]["assumptions"]["tables"] == ["products"]
    assert card["verity"]["confidence"] is not None


def test_capture_card_clarified(gallery_settings: Settings) -> None:
    responses: list[BaseModel] = [
        SqlGeneration(sql=_GOOD, explanation="naive answers anyway"),
        AmbiguityReport(
            needs_clarification=True,
            dimensions=["metric"],
            clarifying_question="Which?",
            options=["a", "b"],
        ),
    ]
    card = run_gallery.capture_card(
        _item(),
        client=FakeLLMClient(responses),
        model="claude-sonnet-4-6",
        settings=gallery_settings,
    )
    # Naive answers the ambiguous question; Verity declines and asks.
    assert card["naive"]["error"] is None
    assert card["verity"]["kind"] == "clarification"
    assert card["verity"]["clarification"]["options"] == ["a", "b"]
