"""Prompt Data FastAPI application entry point.

Phase 0: /health. Phase 1: /ask (non-streaming). Phase 4: /ask/stream (SSE, per-stage).

This module must never import pandas, numpy, torch, transformers, or any model
weights, and keeps the Anthropic SDK lazily imported (see llm.py). The 4 GB RAM
ceiling depends on the server process staying lean; see backend/tests/test_server_rss.py.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.llm import LLMClient, get_llm_client
from backend.app.pipeline.answer import TrustedResponse, respond, respond_events

app = FastAPI(title="Prompt Data", version="0.1.0")

# The frontend normally calls a same-origin /api proxy (Next rewrite); CORS is a dev fallback
# for calling the backend origin directly. Lightweight starlette middleware (no RAM impact).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str
    clarification_answer: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by the RSS test and deployment health checks."""
    return {"status": "ok", "version": "0.1.0"}


def _serialize(result: TrustedResponse) -> dict[str, Any]:
    payload = asdict(result)
    if result.answer is not None:
        payload["answer"]["rows"] = [list(row) for row in result.answer.rows]
    return payload


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Serialize a pipeline StageEvent (which holds dataclass objects) to a JSON-ready dict."""
    etype = event["type"]
    if etype == "stage":
        return {"type": "stage", "name": event["name"], "label": event["label"]}
    if etype == "clarification":
        return {"type": "clarification", "clarification": asdict(event["clarification"])}
    answer = event["answer"]
    answer_dict = asdict(answer)
    answer_dict["rows"] = [list(row) for row in answer.rows]
    return {
        "type": "answer",
        "answer": answer_dict,
        "assumptions": asdict(event["assumptions"]) if event["assumptions"] else None,
        "confidence": asdict(event["confidence"]) if event["confidence"] else None,
    }


@app.post("/ask")
async def ask(
    request: AskRequest,
    client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Answer one question or return a clarifying question. Non-streaming JSON."""
    result = respond(
        request.question,
        client=client,
        settings=settings,
        clarification_answer=request.clarification_answer,
    )
    return _serialize(result)


@app.post("/ask/stream")
def ask_stream(
    request: AskRequest,
    client: Annotated[LLMClient, Depends(get_llm_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Stream the trust pipeline as Server-Sent Events: stage updates, then a terminal result.

    A sync endpoint + sync generator, so Starlette iterates it in a threadpool (the blocking
    Anthropic calls do not block the event loop). One uvicorn worker; low concurrency by design.
    """

    def event_stream() -> Iterator[str]:
        for event in respond_events(
            request.question,
            client=client,
            settings=settings,
            clarification_answer=request.clarification_answer,
        ):
            yield f"data: {json.dumps(_event_payload(event))}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
