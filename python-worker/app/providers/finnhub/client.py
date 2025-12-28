"""Finnhub Provider Client
Implements all HTTP logic, retries, rate limiting, and response normalization.
Follows the clean architecture pattern.
"""

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from app.config import settings
from app.utils.rate_limiter import RateLimiter
from app.observability.logging import get_logger

logger = get_logger("finnhub_client")


@dataclass
class FinnhubConfig:
    api_key: str
    base_url: str = "https://finnhub.io/api/v1"
    timeout: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0
    rate_limit_calls: int = 50
    rate_limit_window: float = 60.0


class FinnhubClient:
    def __init__(self, config: FinnhubConfig):
        if not config.api_key:
            raise ValueError("Finnhub API key is required")

        self.config = config
        self.session = requests.Session()
        self._rate_limiter = RateLimiter(
            max_calls=config.rate_limit_calls,
            time_window=config.rate_limit_window,
            name="Finnhub",
        )

    @classmethod
    def from_settings(cls, api_key: Optional[str] = None) -> "FinnhubClient":
        resolved = api_key or getattr(settings, "finnhub_api_key", None)
        if not resolved:
            raise ValueError("Finnhub API key is required")
        return cls(FinnhubConfig(api_key=resolved))

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        params["token"] = self.config.api_key

        for attempt in range(self.config.max_retries):
            try:
                self._rate_limiter.acquire()
                resp = self.session.get(
                    f"{self.config.base_url}{path}",
                    params=params,
                    timeout=self.config.timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise

    def fetch_current_price(self, symbol: str) -> Optional[float]:
        try:
            data = self._get("/quote", {"symbol": symbol})
            price = data.get("c")
            return float(price) if price is not None else None
        except Exception as e:
            logger.warning(f"Failed to fetch current price for {symbol} from Finnhub: {e}")
            return None

    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        try:
            data = self._get("/stock/profile2", {"symbol": symbol})
            if not isinstance(data, dict) or not data:
                return {}
            return {
                "symbol": symbol,
                "name": data.get("name"),
                "exchange": data.get("exchange"),
                "country": data.get("country"),
                "currency": data.get("currency"),
                "industry": data.get("finnhubIndustry") or data.get("industry"),
                "market_cap": data.get("marketCapitalization"),
                "website": data.get("weburl"),
                "logo": data.get("logo"),
                "ipo": data.get("ipo"),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch symbol details for {symbol} from Finnhub: {e}")
            return {}

    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=7)
            data = self._get(
                "/company-news",
                {
                    "symbol": symbol,
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                },
            )
            if not isinstance(data, list):
                return []
            out: List[Dict[str, Any]] = []
            for item in data[:limit]:
                out.append(
                    {
                        "title": item.get("headline", ""),
                        "publisher": item.get("source", "finnhub"),
                        "link": item.get("url", ""),
                        "published_date": (
                            datetime.fromtimestamp(item.get("datetime", 0))
                            if item.get("datetime")
                            else None
                        ),
                        "summary": item.get("summary", ""),
                        "related_symbols": [symbol],
                        "source": "finnhub",
                    }
                )
            return out
        except Exception as e:
            logger.warning(f"Failed to fetch news for {symbol} from Finnhub: {e}")
            return []

    def fetch_analyst_ratings(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            data = self._get("/stock/recommendation", {"symbol": symbol})
            if not isinstance(data, list):
                return []

            ratings: List[Dict[str, Any]] = []
            for item in data:
                # Finnhub returns counts per period; normalize into a single row-style payload.
                ratings.append(
                    {
                        "symbol": symbol,
                        "period": item.get("period"),
                        "strong_buy": item.get("strongBuy"),
                        "buy": item.get("buy"),
                        "hold": item.get("hold"),
                        "sell": item.get("sell"),
                        "strong_sell": item.get("strongSell"),
                        "source": "finnhub",
                    }
                )
            return ratings
        except Exception as e:
            logger.warning(f"Failed to fetch analyst ratings for {symbol} from Finnhub: {e}")
            return []

    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        try:
            data = self._get("/stock/earnings", {"symbol": symbol})
            if not isinstance(data, list):
                return []
            out: List[Dict[str, Any]] = []
            for item in data[:20]:
                out.append(
                    {
                        "symbol": symbol,
                        "earnings_date": item.get("date"),
                        "eps_estimate": item.get("epsEstimate"),
                        "eps_actual": item.get("epsActual"),
                        "revenue_estimate": item.get("revenueEstimate"),
                        "revenue_actual": item.get("revenueActual"),
                        "surprise_percentage": item.get("surprisePercent"),
                        "source": "finnhub",
                    }
                )
            return out
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {symbol} from Finnhub: {e}")
            return []

    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        # Finnhub free endpoints are limited; reuse profile2 fields as a fundamentals-like payload.
        return self.fetch_symbol_details(symbol)

    def fetch_price_data(self, symbol: str, **kwargs):
        raise NotImplementedError("Use Yahoo/Massive for historical price data")

    def fetch_technical_indicators(self, symbol: str, indicator_type: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Finnhub does not provide technical indicators in this project")

    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        details = self.fetch_symbol_details(symbol)
        return {
            "sector": details.get("sector"),
            "industry": details.get("industry"),
            "peers": [],
        }

    def is_available(self) -> bool:
        try:
            # lightweight check
            _ = self._get("/quote", {"symbol": "AAPL"})
            return True
        except Exception as e:
            logger.warning(f"Finnhub availability check failed: {e}")
            return False
