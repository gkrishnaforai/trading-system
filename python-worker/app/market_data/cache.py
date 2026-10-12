"""Shared canonical market-data cache and in-flight request coalescing."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Awaitable, Callable, Dict, Optional

from app.utils.cache import CacheManager
from app.observability.logging import get_logger

logger = get_logger("canonical_market_cache")


class CanonicalMarketDataCache:
    """Process-shared cache for canonical provider payloads.

    The cache stores serialized canonical models, never provider-specific raw
    responses. In-flight requests with the same key share one provider call.
    """

    TTL_SECONDS = {
        "ohlcv:1d": 24 * 60 * 60,
        "ohlcv:intraday": 60,
        "quote": 60,
        "profile": 7 * 24 * 60 * 60,
        "fundamentals": 24 * 60 * 60,
        "news": 15 * 60,
        "earnings": 6 * 60 * 60,
        "financial_statements": 7 * 24 * 60 * 60,
        "analyst_grades": 60 * 60,
        "price_target": 60 * 60,
    }

    def __init__(self) -> None:
        self._cache = CacheManager(prefix="canonical_market")
        self._inflight: Dict[str, asyncio.Task] = {}
        self.hits = 0
        self.misses = 0
        self.shared = 0

    @staticmethod
    def key(capability: str, symbol: str, **dimensions: Any) -> str:
        payload = {"capability": capability, "symbol": symbol.upper(), **dimensions}
        canonical = json.dumps(payload, sort_keys=True, default=str).encode()
        digest = hashlib.sha256(canonical).hexdigest()[:24]
        return f"v1:{capability}:{symbol.upper()}:{digest}"

    def ttl(self, capability: str, interval: Optional[str] = None) -> int:
        if capability == "ohlcv":
            return self.TTL_SECONDS["ohlcv:intraday" if interval and interval != "1d" else "ohlcv:1d"]
        return self.TTL_SECONDS.get(capability, 300)

    async def get_or_fetch(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        ttl: int,
    ) -> tuple[Any, bool]:
        cached = self._cache.get(key)
        if cached is not None:
            self.hits += 1
            return cached, True

        self.misses += 1
        current = asyncio.current_task()
        existing = self._inflight.get(key)
        if existing is not None and existing is not current:
            self.shared += 1
            return await existing, False

        task = asyncio.create_task(loader())
        self._inflight[key] = task
        try:
            value = await task
            self._cache.set(key, value, ttl=ttl)
            return value, False
        finally:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "shared": self.shared, **self._cache.get_stats()}


_cache = CanonicalMarketDataCache()


def get_market_data_cache() -> CanonicalMarketDataCache:
    return _cache
