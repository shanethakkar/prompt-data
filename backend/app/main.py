"""Verity FastAPI application entry point.

Phase 0: /health. Phase 1 adds /ask (non-streaming). Streaming is Phase 4.

This module must never import pandas, numpy, torch, transformers, or any model
weights. The 4 GB RAM ceiling depends on the server process staying lean; see
backend/tests/test_server_rss.py for the runtime enforcement of that constraint.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.llm import LLMClient, get_llm_client
from backend.app.pipeline.answer import TrustedResponse, respond

app = FastAPI(title="Verity", version="0.1.0")


class AskRequest(BaseModel):
    question: str
    clarification_answer: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by the RSS test and deployment health checks."""
    return {"status": "ok", "version": "0.1.0"}


def _serialize(result: TrustedResponse) -> dict[str, Any]:
    payload = asdict(result)
    # Rows are tuples; JSON wants lists.
    if result.answer is not None:
        payload["answer"]["rows"] = [list(row) for row in result.answer.rows]
    return payload


@app.post("/ask")
async def ask(
    request: AskRequest,
    client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Answer one question or return a clarifying question. Non-streaming; streaming is Phase 4."""
    result = respond(
        request.question,
        client=client,
        settings=settings,
        clarification_answer=request.clarification_answer,
    )
    return _serialize(result)
