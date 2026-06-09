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

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.config import Settings, get_settings
from backend.app.llm import LLMClient, get_llm_client
from backend.app.pipeline.answer import TrustedResponse, respond, respond_events
from backend.app.pipeline.schema import schema_tables
from backend.app.ratelimit import RateLimiter, RateLimitError

app = FastAPI(title="Prompt Data", version="0.1.0")

# In production the browser calls this origin directly (NEXT_PUBLIC_API_BASE), so CORS must
# allow the deployed frontend origin; set CORS_ORIGINS to the Vercel URL. Defaults to localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Process-local guard (single worker) protecting the Anthropic budget on the public /ask routes.
_LIMITER = RateLimiter(get_settings().rate_limit_per_minute, get_settings().daily_request_cap)


def _client_ip(request: Request) -> str:
    """First hop of X-Forwarded-For (set by Render's proxy), else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_guard(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Dependency on the /ask routes. Disabled when both limits are <= 0 (tests)."""
    if settings.rate_limit_per_minute <= 0 and settings.daily_request_cap <= 0:
        return
    try:
        _LIMITER.check(_client_ip(request))
    except RateLimitError as exc:
        raise HTTPException(
            status_code=429, detail=exc.message, headers={"Retry-After": str(exc.retry_after)}
        ) from exc


class AskRequest(BaseModel):
    question: str
    clarification_answer: str | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by the RSS test and deployment health checks."""
    return {"status": "ok", "version": "0.1.0"}


@app.get("/schema")
def schema(
    settings: Annotated[Settings, Depends(get_settings)],
    session: str | None = None,
) -> dict[str, Any]:
    """Structured schema for the active dataset so the UI shows what can be asked.

    `session` selects a bring-your-own-data upload (Part C); until then it resolves to Olist.
    """
    _ = session
    tables = [asdict(table) for table in schema_tables(settings.demo_db_path)]
    return {"dataset": "olist", "tables": tables}


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


@app.post("/ask", dependencies=[Depends(rate_guard)])
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


@app.post("/ask/stream", dependencies=[Depends(rate_guard)])
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
