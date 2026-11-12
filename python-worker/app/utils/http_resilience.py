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
