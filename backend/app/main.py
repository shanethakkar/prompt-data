"""Verity FastAPI application entry point.

Phase 0: /health. Phase 1 adds /ask (non-streaming). Streaming is Phase 4.

This module must never import pandas, numpy, torch, transformers, or any model
weights. The 4 GB RAM ceiling depends on the server process staying lean; see
backend/tests/test_server_rss.py for the runtime enforcement of that constraint.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.llm import LLMClient, get_llm_client
from backend.app.pipeline.answer import answer_question

app = FastAPI(title="Verity", version="0.1.0")


class AskRequest(BaseModel):
    question: str


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by the RSS test and deployment health checks."""
    return {"status": "ok", "version": "0.1.0"}


@app.post("/ask")
async def ask(
    request: AskRequest,
    client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Answer one question. Non-streaming JSON; streaming UI lands in Phase 4."""
    result = answer_question(request.question, client=client, settings=settings)
    return {
        "question": result.question,
        "explanation": result.explanation,
        "sql": result.sql,
        "columns": result.columns,
        "rows": [list(row) for row in result.rows],
        "row_count": result.row_count,
        "chart_type": result.chart_type,
        "self_correction_fired": result.self_correction_fired,
        "attempts": result.attempts,
        "timed_out": result.timed_out,
        "error": result.error,
    }
