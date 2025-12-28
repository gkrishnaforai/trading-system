from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Dict


@dataclass
class ExceptionContext:
    provider: Optional[str] = None
    operation: Optional[str] = None
    symbol: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class ObservabilityError(Exception):
    """Base class for observability-related errors."""


class ProviderError(Exception):
    """Base class for provider (external API/SDK) errors."""

    def __init__(self, message: str, *, context: Optional[ExceptionContext] = None):
        super().__init__(message)
        self.context = context


class ProviderAuthError(ProviderError):
    """Authentication/authorization failure."""


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded."""


class ProviderRequestError(ProviderError):
    """Network/transport/request failure (timeouts, 4xx/5xx, DNS, etc.)."""


class ProviderParseError(ProviderError):
    """Unexpected payload/shape or parsing error."""
