"""In-memory rate/spend guard for the public /ask endpoints.

A public /ask spends the Anthropic budget per request, so the deployed server caps usage:
a per-IP sliding window (requests/minute) plus a global daily request cap. The server runs a
single uvicorn worker (see CLAUDE.md), so process-local state is the whole picture; this is not
correct for a multi-worker deploy. The clock is injectable for testing.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimitError(Exception):
    """Raised when a request exceeds the per-IP window or the global daily cap."""

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class RateLimiter:
    def __init__(
        self, per_minute: int, daily_cap: int, clock: Callable[[], float] = time.time
    ) -> None:
        self.per_minute = per_minute
        self.daily_cap = daily_cap
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._day = int(clock() // 86400)
        self._day_count = 0

    def check(self, ip: str) -> None:
        """Record one request from ip; raise RateLimitError if a limit is exceeded."""
        with self._lock:
            now = self._clock()

            # Reset the global counter at the UTC day boundary.
            day = int(now // 86400)
            if day != self._day:
                self._day = day
                self._day_count = 0
                self._hits.clear()

            if self.daily_cap > 0 and self._day_count >= self.daily_cap:
                raise RateLimitError(
                    "The demo's daily question limit has been reached. Please try again tomorrow.",
                    retry_after=3600,
                )

            hits = self._hits[ip]
            cutoff = now - 60
            while hits and hits[0] < cutoff:
                hits.popleft()

            if self.per_minute > 0 and len(hits) >= self.per_minute:
                retry_after = max(int(60 - (now - hits[0])) + 1, 1)
                raise RateLimitError(
                    "You're sending questions a little fast. Please wait a moment and try again.",
                    retry_after=retry_after,
                )

            hits.append(now)
            self._day_count += 1
