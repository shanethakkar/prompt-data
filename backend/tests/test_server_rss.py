"""Idle server RSS measurement.

Starts uvicorn as a real subprocess, waits for /health, measures the process
RSS with psutil, and asserts it stays under the 4 GB ceiling. A subprocess is
required (not TestClient) so the measurement reflects the real server process,
not the test runner. This is the automated enforcement of the 4 GB constraint:
if pandas, torch, or a model is ever imported at server startup, this fails.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import psutil
import pytest

RSS_LIMIT_MB: int = 4096
SERVER_PORT: int = 8765
STARTUP_TIMEOUT_S: float = 15.0
POLL_INTERVAL_S: float = 0.25

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def server_process() -> Iterator[subprocess.Popen[bytes]]:
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(SERVER_PORT),
            "--workers",
            "1",
        ],
        cwd=str(_PROJECT_ROOT),
    )

    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    started = False
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=1.0)
            if resp.status_code == 200:
                started = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(POLL_INTERVAL_S)

    if not started:
        proc.terminate()
        proc.wait(timeout=5)
        pytest.fail(f"Server did not become healthy within {STARTUP_TIMEOUT_S}s")

    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_idle_server_rss_under_limit(server_process: subprocess.Popen[bytes]) -> None:
    ps_proc = psutil.Process(server_process.pid)
    rss_mb = ps_proc.memory_info().rss / (1024 * 1024)

    print(f"\n[RSS] Idle server RSS: {rss_mb:.1f} MB (limit: {RSS_LIMIT_MB} MB)")

    assert rss_mb < RSS_LIMIT_MB, (
        f"Server RSS {rss_mb:.1f} MB exceeds {RSS_LIMIT_MB} MB. "
        "Check for unexpected heavy imports (pandas, torch, transformers) in the server."
    )
