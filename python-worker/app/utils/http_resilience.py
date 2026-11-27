"""External-call resilience primitives — jitter + circuit breaker.

jitter():     spreads retry sleeps so concurrent workers don't
              retry in lockstep (thundering herd).
breaker():    per-provider circuit breaker — N consecutive failures
              trips it open; calls fail fast for the cooldown, then
              a single probe passes to test recovery.

Both are deliberately tiny and in-memory — jobs are the only
callers and a restart resetting the state is acceptable (the next
failure streak simply trips it again).
"""
from __future__ import annotations

import logging
import random
from typing import Optional
import time

logger = logging.getLogger(__name__)


def jitter(delay: float) -> float:
    """±50% variance on a backoff sleep."""
    return delay * random.uniform(0.5, 1.5)


class ProviderDown(Exception):
    """Raised when the circuit is open — fail fast, don't wait out
    the full timeout on a provider that's already dead."""


class CircuitBreaker:
    """threshold consecutive failures → open for cooldown, then a
    single half-open probe; success closes it."""

    def __init__(self, threshold: int = 5, cooldown: float = 300.0):
        self.threshold, self.cooldown = threshold, cooldown
        self._fails = 0
        self._open_until = 0.0

    def allow(self) -> bool:
        return time.monotonic() >= self._open_until

    def success(self) -> None:
        self._fails = 0
        self._open_until = 0.0

    def failure(self) -> None:
        self._fails += 1
        if self._fails >= self.threshold:
            self._open_until = time.monotonic() + self.cooldown
            self._fails = 0          # half-open: next call probes
            logger.warning(
                "circuit open %ss — provider tripped after %d "
                "consecutive failures", self.cooldown, self.threshold)


_breakers: dict[str, CircuitBreaker] = {}


def breaker(name: str, threshold: int = 5,
            cooldown: float = 300.0) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(threshold, cooldown)
    return _breakers[name]


def log_failure(provider: str, endpoint: str, error: str,
                latency_ms: Optional[int] = None) -> None:
    """Terminal provider failure → fetch_failures ledger. Cheap,
    best-effort (never raises — a ledger write must not become a
    second failure mode). The ops surfaces read this to distinguish
    'transient blip' from 'provider down since 9:40'."""
    try:
        from app.database import db
        db.execute_update(
            "CREATE TABLE IF NOT EXISTS fetch_failures ("
            " id bigserial PRIMARY KEY, provider TEXT NOT NULL,"
            " endpoint TEXT NOT NULL, error TEXT NOT NULL,"
            " latency_ms INT,"
            " occurred_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        db.execute_update(
            "INSERT INTO fetch_failures"
            " (provider, endpoint, error, latency_ms)"
            " VALUES (:p, :e, :r, :l)",
            {"p": provider, "e": endpoint, "r": error[:500],
             "l": latency_ms})
        db.execute_update(
            "DELETE FROM fetch_failures"
            " WHERE occurred_at < now() - interval '30 days'")
    except Exception as exc:
        logger.debug("fetch_failures write failed: %s", exc)


def fail(provider: str, endpoint: str, error: Exception,
         latency_ms: Optional[int] = None) -> None:
    """One call — ledger the failure AND trip the breaker. Use at
    terminal-raise sites, not per-attempt (a retried blip isn't an
    outage)."""
    log_failure(provider, endpoint, str(error), latency_ms)
    breaker(provider).failure()
