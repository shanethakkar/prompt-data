"""Verity FastAPI application entry point.

Phase 0: /health only. The text-to-SQL pipeline is wired in Phase 1.

This module must never import pandas, numpy, torch, transformers, or any model
weights. The 4 GB RAM ceiling depends on the server process staying lean; see
backend/tests/test_server_rss.py for the runtime enforcement of that constraint.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Verity", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by the RSS test and deployment health checks."""
    return {"status": "ok", "version": "0.1.0"}
