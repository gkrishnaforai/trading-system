"""
MarketDataService — the facade upper layers (quant, agents) call.

Wraps ProviderRouter and softens the contract:
- DataNotFound          -> None / []  (a definitive "no data" answer)
- MarketDataUnavailable -> propagates (every provider failed — caller decides)
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Dict, List, Optional

from app.config import settings
from app.observability.logging import get_logger

from .base import MarketDataProvider
from .cache import get_market_data_cache
from .errors import (
    DataNotFound,
    DataQualityError,
    MarketDataUnavailable,
    ProviderAttempt,
)
from .models import (
    AnalystGrade,
    CompanyProfile,
    EarningsEvent,
    FinancialEstimate,
    FinancialStatements,
    FundamentalsSnapshot,
    MarketData,
    NewsItem,
    OHLCVBar,
    PriceTarget,
    Quote,
)
from .policy import DAILY_INTERVALS, normalize_bars
from .router import ProviderRouter
from .validation import validate_bars

logger = get_logger("market_data_service")


def build_providers() -> Dict[str, MarketDataProvider]:
    """Instantiate adapters for configured providers. Missing keys/libs -> skipped."""
    providers: Dict[str, MarketDataProvider] = {}

    if (getattr(settings, "fmp_api_key", "") or "").strip():
        try:
            from .providers.fmp import FMPProvider

            providers["fmp"] = FMPProvider()
        except Exception as e:
            logger.warning(f"FMP provider unavailable: {e}")

    try:
        from .providers.yahoo import YahooProvider

        providers["yahoo_finance"] = YahooProvider()
    except Exception as e:
        logger.warning(f"Yahoo provider unavailable: {e}")

    if getattr(settings, "massive_enabled", False) and getattr(
        settings, "massive_api_key", None
    ):
        try:
            from .providers.massive import MassiveProvider

            providers["massive"] = MassiveProvider()
        except Exception as e:
            logger.warning(f"Massive provider unavailable: {e}")

    return providers


class MarketDataService:
    """Single entry point for market data. Owns the router and attempt log."""

    def __init__(
        self,
        router: Optional[ProviderRouter] = None,
        on_attempt: Optional[Callable[[ProviderAttempt], None]] = None,
    ):
        self.router = router or ProviderRouter(
            providers=build_providers(), on_attempt=on_attempt
        )
        self.cache = get_market_data_cache()

    def _cache_key(self, capability: str, symbol: str, **dimensions: Any) -> str:
        dimensions["provider_route"] = tuple(self.chain_for(capability))
        return self.cache.key(capability, symbol, **dimensions)

    # --- capabilities ---

    async def get_ohlcv(
        self,
        symbol: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        period: Optional[str] = None,
        interval: str = "1d",
        prefer: Optional[List[str]] = None,
    ) -> List[OHLCVBar]:
        """Canonical bars from the routed provider, normalized per price policy.

        `prefer` reorders the chain for this call only (e.g. ["yahoo_finance"]
        for symbols FMP doesn't cover on the current plan).
        """
        key = self._cache_key(
            "ohlcv", symbol, start=start, end=end, period=period,
            interval=interval, prefer=tuple(prefer or ()),
        )

        async def load() -> list[dict[str, Any]]:
            try:
                bars = await self.router.get_ohlcv(
                    symbol, start=start, end=end, period=period, interval=interval,
                    prefer=prefer,
                )
            except DataNotFound:
                return []
            return [bar.model_dump(mode="json") for bar in normalize_bars(bars, interval)]

        payload, _ = await self.cache.get_or_fetch(
            key, load, ttl=self.cache.ttl("ohlcv", interval)
        )
        return [OHLCVBar.model_validate(item) for item in payload]

    async def get_market_data(
        self,
        symbol: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
        period: Optional[str] = None,
        interval: str = "1d",
        min_bars: int = 1,
        validate: bool = True,
        strict: bool = False,
    ) -> Optional[MarketData]:
        """Provider-routed bars + quality report in one aggregate.

        strict=True raises DataQualityError on error-severity issues instead of
        returning data with a failing report.
        """
        bars = await self.get_ohlcv(
            symbol, start=start, end=end, period=period, interval=interval
        )
        if not bars:
            return None

        report = None
        if validate:
            report = validate_bars(
                bars,
                symbol=symbol,
                provider=bars[0].provider,
                interval=interval,
                min_bars=min_bars,
                stale_after_days=10 if interval in DAILY_INTERVALS else None,
            )
            if strict and not report.ok:
                raise DataQualityError(report)

        return MarketData(
            provider=bars[0].provider,
            symbol=symbol,
            interval=interval,
            bars=bars,
            quality=report.model_dump() if report else None,
        )

    async def get_quote(self, symbol: str) -> Optional[Quote]:
        key = self._cache_key("quote", symbol)

        async def load() -> Optional[dict[str, Any]]:
            try:
                value = await self.router.get_quote(symbol)
                return value.model_dump(mode="json") if value else None
            except DataNotFound:
                return None

        payload, _ = await self.cache.get_or_fetch(key, load, ttl=self.cache.ttl("quote"))
        return Quote.model_validate(payload) if payload else None

    async def get_profile(self, symbol: str) -> Optional[CompanyProfile]:
        key = self._cache_key("profile", symbol)

        async def load() -> Optional[dict[str, Any]]:
            try:
                value = await self.router.get_profile(symbol)
                return value.model_dump(mode="json") if value else None
            except DataNotFound:
                return None

        payload, _ = await self.cache.get_or_fetch(key, load, ttl=self.cache.ttl("profile"))
        return CompanyProfile.model_validate(payload) if payload else None

    async def get_fundamentals(self, symbol: str) -> Optional[FundamentalsSnapshot]:
        key = self._cache_key("fundamentals", symbol)

        async def load() -> Optional[dict[str, Any]]:
            try:
                value = await self.router.get_fundamentals(symbol)
                return value.model_dump(mode="json") if value else None
            except DataNotFound:
                return None

        payload, _ = await self.cache.get_or_fetch(key, load, ttl=self.cache.ttl("fundamentals"))
        return FundamentalsSnapshot.model_validate(payload) if payload else None

    async def get_financial_statements(
        self, symbol: str, period: Optional[str] = None
    ) -> Optional[FinancialStatements]:
        key = self._cache_key("financial_statements", symbol, period=period or "annual")

        async def load() -> Optional[dict[str, Any]]:
            try:
                value = await self.router.get_financial_statements(symbol, period=period)
                return value.model_dump(mode="json") if value else None
            except DataNotFound:
                return None

        payload, _ = await self.cache.get_or_fetch(
            key, load, ttl=self.cache.ttl("financial_statements")
        )
        return FinancialStatements.model_validate(payload) if payload else None

    async def get_financial_estimates(self, symbol: str, period: str = "annual", limit: int = 10) -> List[FinancialEstimate]:
        key = self._cache_key("financial_estimates", symbol, period=period, limit=limit)

        async def load() -> list[dict[str, Any]]:
            try:
                values = await self.router.get_financial_estimates(symbol, period=period, limit=limit)
                return [value.model_dump(mode="json") for value in values]
            except DataNotFound:
                return []

        payload, _ = await self.cache.get_or_fetch(key, load, ttl=24 * 60 * 60)
        return [FinancialEstimate.model_validate(item) for item in payload]

    async def get_news(self, symbol: str, limit: int = 10) -> List[NewsItem]:
        key = self._cache_key("news", symbol, limit=limit)

        async def load() -> list[dict[str, Any]]:
            try:
                values = await self.router.get_news(symbol, limit=limit)
                return [value.model_dump(mode="json") for value in values]
            except DataNotFound:
                return []

        payload, _ = await self.cache.get_or_fetch(key, load, ttl=self.cache.ttl("news"))
        return [NewsItem.model_validate(item) for item in payload]

    async def get_earnings(self, symbol: str) -> List[EarningsEvent]:
        key = self._cache_key("earnings", symbol)

        async def load() -> list[dict[str, Any]]:
            try:
                values = await self.router.get_earnings(symbol)
                return [value.model_dump(mode="json") for value in values]
            except DataNotFound:
                return []

        payload, _ = await self.cache.get_or_fetch(key, load, ttl=self.cache.ttl("earnings"))
        return [EarningsEvent.model_validate(item) for item in payload]

    async def get_analyst_grades(self, symbol: str) -> List[AnalystGrade]:
        try:
            return await self.router.get_analyst_grades(symbol)
        except DataNotFound:
            return []

    async def get_price_target(self, symbol: str) -> Optional[PriceTarget]:
        try:
            return await self.router.get_price_target(symbol)
        except DataNotFound:
            return None

    # --- introspection ---

    @property
    def providers(self) -> List[str]:
        return list(self.router._providers)

    def chain_for(self, capability: str) -> List[str]:
        """Effective provider order for a capability."""
        return self.router.chain_for(capability)

    @property
    def attempts(self) -> List[ProviderAttempt]:
        return self.router.attempts

    @property
    def cache_stats(self) -> Dict[str, int]:
        return self.cache.stats()

    async def health(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for name, provider in self.router._providers.items():
            try:
                result[name] = {"available": await provider.is_available()}
            except Exception as e:
                result[name] = {"available": False, "error": str(e)}
        return result


_service: Optional[MarketDataService] = None


def get_market_data_service() -> MarketDataService:
    """Lazy singleton."""
    global _service
    if _service is None:
        _service = MarketDataService()
    return _service
