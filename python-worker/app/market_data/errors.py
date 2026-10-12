"""
Typed errors for the market data layer.

The provider contract depends on the distinction between:
- ProviderError:        transport/auth/rate-limit failure -> try next provider
- DataNotFound:         provider answered, but has no data -> router decides per route
- UnsupportedCapability: provider doesn't offer this data  -> skip silently
- MarketDataUnavailable: every provider in the chain failed -> raised to caller
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .validation import DataQualityReport


class ProviderError(Exception):
    """A provider call failed (network, auth, rate limit, malformed response)."""

    def __init__(
        self,
        provider: str,
        capability: str,
        message: str,
        *,
        retryable: bool = True,
        cause: Optional[Exception] = None,
    ):
        self.provider = provider
        self.capability = capability
        self.retryable = retryable
        self.cause = cause
        super().__init__(f"[{provider}/{capability}] {message}")


class DataNotFound(ProviderError):
    """The provider answered successfully but has no data for this request."""

    def __init__(self, provider: str, capability: str, message: str = "no data"):
        super().__init__(provider, capability, message, retryable=False)


class UnsupportedCapability(ProviderError):
    """The provider does not implement this capability at all."""

    def __init__(self, provider: str, capability: str):
        super().__init__(
            provider, capability, "capability not supported", retryable=False
        )


@dataclass
class ProviderAttempt:
    """Record of a single provider attempt — feed this to tracing (Langfuse) later."""

    provider: str
    capability: str
    ok: bool
    latency_ms: float
    error: Optional[str] = None
    error_type: Optional[str] = None
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MarketDataUnavailable(Exception):
    """Every provider in the routing chain failed for this capability."""

    def __init__(self, capability: str, symbol: str, attempts: List[ProviderAttempt]):
        self.capability = capability
        self.symbol = symbol
        self.attempts = list(attempts)
        tried = ", ".join(
            f"{a.provider}({a.error_type or 'ok'})" for a in self.attempts
        )
        super().__init__(
            f"No provider could serve '{capability}' for {symbol}. "
            f"Attempts: {tried or 'none'}"
        )


class DataQualityError(Exception):
    """Bars failed quality validation (raised only in strict mode)."""

    def __init__(self, report: "DataQualityReport"):
        self.report = report
        msgs = "; ".join(i.message for i in report.errors)
        super().__init__(
            f"Data quality check failed for {report.symbol} "
            f"({report.provider}): {msgs or 'unknown'}"
        )
