"""Runtime settings, loaded from the environment (.env in local dev).

Centralizes the few knobs the pipeline needs so they are not scattered as
literals across modules. Import get_settings(), do not read os.environ directly
elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable view of the process configuration."""

    anthropic_api_key: str | None
    demo_db_path: str
    generation_model: str
    sql_default_limit: int
    sql_timeout_seconds: float
    max_self_correction_attempts: int
    self_consistency_samples: int
    self_consistency_temperature: float
    calibration_path: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        demo_db_path=os.environ.get("DEMO_DB_PATH", "data/demo.db"),
        generation_model=os.environ.get("GENERATION_MODEL", "claude-sonnet-4-6"),
        sql_default_limit=int(os.environ.get("SQL_DEFAULT_LIMIT", "500")),
        sql_timeout_seconds=float(os.environ.get("SQL_TIMEOUT_SECONDS", "10")),
        max_self_correction_attempts=int(os.environ.get("MAX_SELF_CORRECTION_ATTEMPTS", "2")),
        self_consistency_samples=int(os.environ.get("SELF_CONSISTENCY_SAMPLES", "5")),
        self_consistency_temperature=float(os.environ.get("SELF_CONSISTENCY_TEMPERATURE", "0.7")),
        calibration_path=os.environ.get("CALIBRATION_PATH", "eval/out/calibration.json"),
    )
