"""Model routing seam.

Phase 1 uses a single model. This function is where Phase 6 will route fast
questions to a cheaper tier and hard or self-correcting ones to a stronger
model, tracking cost per request. Kept as a seam so callers never hardcode the
model string.
"""

from __future__ import annotations

from backend.app.config import get_settings


def select_model(question: str) -> str:
    _ = question
    return get_settings().generation_model
