"""
Provider contract for the market data layer.

Each adapter wraps one existing provider client (FMP, Yahoo, Massive) and:
- runs the blocking client in a worker thread (asyncio.to_thread)
- normalizes provider payloads into canonical models
- translates outcomes into typed errors:
    UnsupportedCapability -> provider doesn't offer this data
    DataNotFound          -> provider answered, no data
    ProviderError         -> transport/auth/rate-limit failure

The router depends on providers never swallowing errors into empty results.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any, Callable, List, Optional, TypeVar

import pandas as pd

from .errors import DataNotFound, ProviderError, UnsupportedCapability
from .models import (
    AnalystGrade,
    CompanyProfile,
    EarningsEvent,
    FinancialEstimate,
    FinancialStatements,
    FundamentalsSnapshot,
    NewsItem,
    OHLCVBar,
    PriceTarget,
    Quote,
)

T = TypeVar("T")

CAPABILITIES = (
    "ohlcv",
    "quote",
    "profile",
    "fundamentals",
    "financial_statements",
    "financial_estimates",
    "news",
    "earnings",
    "analyst_grades",
    "price_target",
)


def to_date(value: Any) -> Optional[date]:
    """Best-effort parse of provider date values into a date."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date()
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s[:26], fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def to_datetime(value: Any) -> Optional[datetime]:
    """Best-effort parse of provider datetime values into a datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)):
        # FMP quote timestamps are epoch seconds
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except Exception:
            return None
    try:
        return pd.to_datetime(str(value).strip()).to_pydatetime()
    except Exception:
        return to_date(value) and datetime.combine(to_date(value), datetime.min.time())


def to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(value)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> Optional[int]:
    f = to_float(value)
    return int(f) if f is not None else None


def first(data: dict, *keys: str) -> Any:
    """Return the first non-None value among candidate keys."""
    for k in keys:
        v = data.get(k)
        if v is not None and v != "":
            return v
    return None


class MarketDataProvider:
    """
    Base class for provider adapters. Methods raise UnsupportedCapability by
    default — providers override only what they actually offer.
    """

    name: str = "abstract"

    # --- capability surface (override what the provider supports) ---

    async def get_ohlcv(
        self,
        symbol: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        period: Optional[str] = None,
        interval: str = "1d",
    ) -> List[OHLCVBar]:
        raise UnsupportedCapability(self.name, "ohlcv")

    async def get_quote(self, symbol: str) -> Quote:
        raise UnsupportedCapability(self.name, "quote")

    async def get_profile(self, symbol: str) -> CompanyProfile:
        raise UnsupportedCapability(self.name, "profile")

    async def get_fundamentals(self, symbol: str) -> FundamentalsSnapshot:
        raise UnsupportedCapability(self.name, "fundamentals")

    async def get_financial_statements(
        self, symbol: str, period: Optional[str] = None
    ) -> FinancialStatements:
        raise UnsupportedCapability(self.name, "financial_statements")

    async def get_financial_estimates(self, symbol: str, period: str = "annual", limit: int = 10) -> List[FinancialEstimate]:
        raise UnsupportedCapability(self.name, "financial_estimates")

    async def get_news(self, symbol: str, limit: int = 10) -> List[NewsItem]:
        raise UnsupportedCapability(self.name, "news")

    async def get_earnings(self, symbol: str) -> List[EarningsEvent]:
        raise UnsupportedCapability(self.name, "earnings")

    async def get_analyst_grades(self, symbol: str) -> List[AnalystGrade]:
        raise UnsupportedCapability(self.name, "analyst_grades")

    async def get_price_target(self, symbol: str) -> PriceTarget:
        raise UnsupportedCapability(self.name, "price_target")

    async def is_available(self) -> bool:
        return True

    # --- plumbing ---

    def supports(self, capability: str) -> bool:
        """True if this provider overrides the method for `capability`."""
        method_name = f"get_{capability}"
        return getattr(type(self), method_name, None) is not getattr(
            MarketDataProvider, method_name, None
        )

    async def _call(
        self, capability: str, fn: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        """Run a blocking client call off the event loop; wrap failures."""
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(self.name, capability, str(e), cause=e)

    @staticmethod
    def _require(payload: Any, provider: str, capability: str) -> Any:
        """Treat None/empty payloads as DataNotFound."""
        if payload is None:
            raise DataNotFound(provider, capability)
        if isinstance(payload, (list, dict)) and len(payload) == 0:
            raise DataNotFound(provider, capability)
        if isinstance(payload, pd.DataFrame) and payload.empty:
            raise DataNotFound(provider, capability)
        return payload
