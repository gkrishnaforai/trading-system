"""
Massive (Polygon) provider adapter — wraps MassiveClient, normalizes to canonical models.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from app.observability.logging import get_logger
from app.providers.massive.client import MassiveClient

from ..base import MarketDataProvider, first, to_date, to_datetime, to_float
from ..errors import DataNotFound
from ..models import (
    CompanyProfile,
    EarningsEvent,
    NewsItem,
    OHLCVBar,
    Quote,
)

logger = get_logger("market_data_massive")

_TIMESPANS = {
    "1d": ("day", 1),
    "1day": ("day", 1),
    "day": ("day", 1),
    "5m": ("minute", 5),
    "5min": ("minute", 5),
    "1h": ("hour", 1),
    "1w": ("week", 1),
    "1mo": ("month", 1),
}


class MassiveProvider(MarketDataProvider):
    name = "massive"

    def __init__(self, client: Optional[MassiveClient] = None):
        self._client = client or MassiveClient.from_settings()

    async def get_ohlcv(
        self,
        symbol: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        period: Optional[str] = None,
        interval: str = "1d",
    ) -> List[OHLCVBar]:
        timespan, multiplier = _TIMESPANS.get(interval, ("day", 1))
        from_date = (
            start.isoformat() if isinstance(start, date) else start
        ) or "2024-01-01"
        to_date_s = (end.isoformat() if isinstance(end, date) else end) or datetime.now().strftime("%Y-%m-%d")

        df = self._require(
            await self._call(
                "ohlcv",
                self._client.fetch_price_data,
                symbol,
                from_date=from_date,
                to_date=to_date_s,
                timespan=timespan,
                multiplier=multiplier,
            ),
            self.name,
            "ohlcv",
        )
        bars = [
            OHLCVBar(
                provider=self.name,
                symbol=symbol,
                timestamp=to_datetime(row.get("date")),
                interval=interval,
                open=to_float(row.get("open")),
                high=to_float(row.get("high")),
                low=to_float(row.get("low")),
                close=to_float(row.get("close")),
                volume=to_float(row.get("volume")),
            )
            for row in df.to_dict(orient="records")
        ]
        return self._require(bars, self.name, "ohlcv")

    async def get_quote(self, symbol: str) -> Quote:
        data = self._require(
            await self._call("quote", self._client.fetch_current_price, symbol),
            self.name,
            "quote",
        )
        price = to_float(data.get("price"))
        if price is None:
            raise DataNotFound(self.name, "quote", "no price in quote payload")
        return Quote(
            provider=self.name,
            symbol=symbol,
            price=price,
            volume=to_float(data.get("volume")),
        )

    async def get_profile(self, symbol: str) -> CompanyProfile:
        data = self._require(
            await self._call("profile", self._client.fetch_symbol_details, symbol),
            self.name,
            "profile",
        )
        return CompanyProfile(
            provider=self.name,
            symbol=symbol,
            name=data.get("name"),
            exchange=data.get("exchange"),
            currency=data.get("currency"),
            sector=data.get("sector"),
            industry=data.get("industry"),
            country=data.get("country"),
            market_cap=to_float(data.get("market_cap")),
            description=data.get("description"),
            website=data.get("website"),
        )

    async def get_news(self, symbol: str, limit: int = 10) -> List[NewsItem]:
        rows = self._require(
            await self._call("news", self._client.fetch_news, symbol, limit),
            self.name,
            "news",
        )
        items = [
            NewsItem(
                provider=self.name,
                symbol=symbol,
                title=r.get("title") or "",
                url=first(r, "link", "url"),
                publisher=r.get("publisher"),
                published_at=to_datetime(
                    first(r, "published_date", "published_utc")
                ),
                related_symbols=list(r.get("related_symbols") or [symbol]),
            )
            for r in rows
            if isinstance(r, dict)
        ]
        return self._require(items, self.name, "news")

    async def get_earnings(self, symbol: str) -> List[EarningsEvent]:
        rows = self._require(
            await self._call("earnings", self._client.fetch_earnings, symbol),
            self.name,
            "earnings",
        )
        events = [
            EarningsEvent(
                provider=self.name,
                symbol=symbol,
                date=to_date(first(r, "period_end", "date")),
                eps_actual=to_float(
                    first(r, "earnings_per_share", "net_income_per_share")
                ),
                revenue_actual=to_float(first(r, "revenues", "total_revenue")),
                fiscal_period=r.get("fiscal_period"),
                fiscal_year=(
                    int(r["fiscal_year"])
                    if isinstance(r.get("fiscal_year"), (int, float))
                    else None
                ),
            )
            for r in rows
            if isinstance(r, dict)
        ]
        return self._require(events, self.name, "earnings")
