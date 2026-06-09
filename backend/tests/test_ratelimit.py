"""Tests for the in-memory rate/spend guard (injected clock)."""

from __future__ import annotations

import pytest

from backend.app.ratelimit import RateLimiter, RateLimitError


class FakeClock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_per_minute_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=3, daily_cap=0, clock=clock)
    for _ in range(3):
        limiter.check("1.1.1.1")
    with pytest.raises(RateLimitError) as exc:
        limiter.check("1.1.1.1")
    assert exc.value.retry_after >= 1

    # After the window slides past 60s, requests are allowed again.
    clock.t += 61
    limiter.check("1.1.1.1")


def test_per_ip_isolation() -> None:
    limiter = RateLimiter(per_minute=2, daily_cap=0, clock=FakeClock())
    limiter.check("a")
    limiter.check("a")
    # A different IP has its own window.
    limiter.check("b")
    limiter.check("b")
    with pytest.raises(RateLimitError):
        limiter.check("a")


def test_daily_cap_and_rollover() -> None:
    clock = FakeClock()
    limiter = RateLimiter(per_minute=0, daily_cap=2, clock=clock)
    limiter.check("a")
    limiter.check("b")  # global cap counts across IPs
    with pytest.raises(RateLimitError) as exc:
        limiter.check("c")
    assert "daily" in exc.value.message.lower()

    # Next UTC day resets the global counter.
    clock.t += 86_400
    limiter.check("c")


def test_zero_limits_are_unlimited() -> None:
    limiter = RateLimiter(per_minute=0, daily_cap=0, clock=FakeClock())
    for _ in range(50):
        limiter.check("a")  # no exception
