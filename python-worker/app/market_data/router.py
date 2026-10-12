"""
ProviderRouter — ordered fallback chain per capability.

Semantics:
- UnsupportedCapability -> skip provider silently (doesn't count as a failure)
- DataNotFound          -> fall through to next provider if the route has
                           fallback_on_empty=True, otherwise it's a definitive
                           "no data" answer and propagates to the caller
- ProviderError         -> record and try next provider
- chain exhausted       -> raise MarketDataUnavailable with the attempt log

Every attempt is recorded in `self.attempts` and pushed to the optional
`on_attempt` observer — this is the hook Langfuse will plug into later.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Awaitable, Callable, Dict, List, Optional, TypeVar

from app.observability.logging import get_logger

from .base import MarketDataProvider
from .config import RouteConfig, load_routes
from .errors import (
    DataNotFound,
    MarketDataUnavailable,
    ProviderAttempt,
    ProviderError,
    UnsupportedCapability,
)
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

logger = get_logger("market_data_router")

T = TypeVar("T")


class ProviderRouter:
    def __init__(
        self,
        providers: Dict[str, MarketDataProvider],
        routes: Optional[Dict[str, RouteConfig]] = None,
        on_attempt: Optional[Callable[[ProviderAttempt], None]] = None,
    ):
        self._providers = providers
        self._routes = routes or load_routes()
        self._on_attempt = on_attempt
        self.attempts: List[ProviderAttempt] = []

    def chain_for(self, capability: str) -> List[str]:
        route = self._routes.get(capability)
        names = route.providers if route else list(self._providers)
        chain = [
            n for n in names
            if n in self._providers and self._providers[n].supports(capability)
        ]
        if not chain:
            # Route names providers that aren't instantiated (missing keys,
            # library, or custom names). Degrade to all capable providers
            # rather than failing closed.
            chain = [
                n for n, p in self._providers.items() if p.supports(capability)
            ]
        return chain

    def _record(self, attempt: ProviderAttempt, into: List[ProviderAttempt]) -> None:
        into.append(attempt)
        self.attempts.append(attempt)
        if self._on_attempt:
            try:
                self._on_attempt(attempt)
            except Exception as e:
                logger.debug(f"on_attempt observer failed: {e}")

    async def _route(
        self,
        capability: str,
        symbol: str,
        call: Callable[[MarketDataProvider], Awaitable[T]],
        prefer: Optional[List[str]] = None,
    ) -> T:
        route = self._routes.get(capability) or RouteConfig(
            providers=list(self._providers)
        )
        attempts: List[ProviderAttempt] = []
        symbol = (symbol or "").strip().upper()

        chain = self.chain_for(capability)
        if prefer:
            # Reorder for this call only: preferred providers first, the
            # rest of the chain preserved as fallback. Used e.g. to send
            # breadth/macro symbols Yahoo-first when FMP doesn't cover them.
            chain = [n for n in prefer if n in chain] + \
                [n for n in chain if n not in prefer]

        for name in chain:
            provider = self._providers[name]

            t0 = time.monotonic()
            try:
                result = await call(provider)
            except UnsupportedCapability:
                continue
            except DataNotFound as e:
                self._record(
                    ProviderAttempt(
                        provider=name,
                        capability=capability,
                        ok=False,
                        latency_ms=(time.monotonic() - t0) * 1000,
                        error=str(e),
                        error_type="data_not_found",
                    ),
                    attempts,
                )
                if not route.fallback_on_empty:
                    raise
                continue
            except ProviderError as e:
                logger.warning(f"Provider {name} failed for {capability}/{symbol}: {e}")
                self._record(
                    ProviderAttempt(
                        provider=name,
                        capability=capability,
                        ok=False,
                        latency_ms=(time.monotonic() - t0) * 1000,
                        error=str(e),
                        error_type="provider_error",
                    ),
                    attempts,
                )
                continue
            except Exception as e:
                logger.warning(f"Provider {name} raised for {capability}/{symbol}: {e}")
                self._record(
                    ProviderAttempt(
                        provider=name,
                        capability=capability,
                        ok=False,
                        latency_ms=(time.monotonic() - t0) * 1000,
                        error=str(e),
                        error_type=type(e).__name__,
                    ),
                    attempts,
                )
                continue

            self._record(
                ProviderAttempt(
                    provider=name,
                    capability=capability,
                    ok=True,
                    latency_ms=(time.monotonic() - t0) * 1000,
                ),
                attempts,
            )
            return result

        raise MarketDataUnavailable(capability, symbol, attempts)

    # --- typed capability methods ---

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
        return await self._route(
            "ohlcv",
            symbol,
            lambda p: p.get_ohlcv(
                symbol, start=start, end=end, period=period, interval=interval
            ),
            prefer=prefer,
        )

    async def get_quote(self, symbol: str) -> Quote:
        return await self._route("quote", symbol, lambda p: p.get_quote(symbol))

    async def get_profile(self, symbol: str) -> CompanyProfile:
        return await self._route("profile", symbol, lambda p: p.get_profile(symbol))

    async def get_fundamentals(self, symbol: str) -> FundamentalsSnapshot:
        return await self._route(
            "fundamentals", symbol, lambda p: p.get_fundamentals(symbol)
        )

    async def get_financial_statements(
        self, symbol: str, period: Optional[str] = None
    ) -> FinancialStatements:
        return await self._route(
            "financial_statements",
            symbol,
            lambda p: p.get_financial_statements(symbol, period=period),
        )

    async def get_financial_estimates(self, symbol: str, period: str = "annual", limit: int = 10) -> List[FinancialEstimate]:
        return await self._route(
            "financial_estimates", symbol,
            lambda p: p.get_financial_estimates(symbol, period=period, limit=limit),
        )

    async def get_news(self, symbol: str, limit: int = 10) -> List[NewsItem]:
        return await self._route(
            "news", symbol, lambda p: p.get_news(symbol, limit=limit)
        )

    async def get_earnings(self, symbol: str) -> List[EarningsEvent]:
        return await self._route(
            "earnings", symbol, lambda p: p.get_earnings(symbol)
        )

    async def get_analyst_grades(self, symbol: str) -> List[AnalystGrade]:
        return await self._route(
            "analyst_grades", symbol, lambda p: p.get_analyst_grades(symbol)
        )

    async def get_price_target(self, symbol: str) -> PriceTarget:
        return await self._route(
            "price_target", symbol, lambda p: p.get_price_target(symbol)
        )
