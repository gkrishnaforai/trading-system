"""
Fallback Data Source — primary-only now.

Historically this silently substituted Finnhub when Yahoo failed — a
licensed source sneaking in behind a primary error. That violates the
no-silent-fallback rule (a caller asking for source A must never get
source B's data without knowing). Fallback branches were removed in
Phase F: a primary failure raises, honestly.

The class name stays — callers import FallbackDataSource — but it is
a Yahoo-primary adapter. In MP_DATA_MODE=public_only every licensed
call is gated at the provider clients upstream.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd

from app.data_sources.base import BaseDataSource
from app.data_sources.yahoo_finance_source import YahooFinanceSource

logger = logging.getLogger(__name__)


class FallbackDataSource(BaseDataSource):
    """
    Yahoo-primary data source. No fallback — a primary failure raises
    rather than silently substituting licensed Finnhub data.
    """

    def __init__(self):
        """Initialize primary source"""
        self.primary_source = YahooFinanceSource()

    @property
    def name(self) -> str:
        return "yahoo_primary"

    def is_available(self) -> bool:
        """Check if data source is available"""
        return self.primary_source.is_available()

    def fetch_price_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y",
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV price data"""
        kwargs: Dict[str, Any] = {"period": period, "interval": interval}
        if start_date and end_date:
            kwargs["start_date"] = start_date
            kwargs["end_date"] = end_date
        return self.primary_source.fetch_price_data(symbol, **kwargs)

    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current/live price with volume"""
        return self.primary_source.fetch_current_price(symbol)

    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data"""
        return self.primary_source.fetch_fundamentals(symbol)

    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles"""
        return self.primary_source.fetch_news(symbol, limit)

    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings calendar and history"""
        return self.primary_source.fetch_earnings(symbol)

    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers and sector data"""
        return self.primary_source.fetch_industry_peers(symbol)
