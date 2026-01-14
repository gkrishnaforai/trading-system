"""
Yahoo Finance Data Source - Thin Adapter
Implements BaseDataSource by delegating to YahooFinanceClient
Follows clean architecture pattern
"""
import logging
from typing import Dict, Any, Optional, List
import pandas as pd

from app.data_sources.base import BaseDataSource
from app.providers.yahoo_finance.client import YahooFinanceClient, YahooFinanceConfig
from app.observability.logging import get_logger

logger = get_logger("yahoo_finance_source")


class YahooFinanceSource(BaseDataSource):
    """
    Yahoo Finance data source - thin adapter
    Delegates all operations to YahooFinanceClient
    """
    
    def __init__(self, config: Optional[YahooFinanceConfig] = None):
        if config is None:
            # Create client from settings
            self._client = YahooFinanceClient.from_settings()
        else:
            self._client = YahooFinanceClient(config)
        
        logger.info("✅ Yahoo Finance Source initialized as thin adapter")
    
    @property
    def name(self) -> str:
        return "yahoo_finance"
    
    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        """Fetch historical price data - delegates to client"""
        # Backward-compatible kwarg mapping: older callers use start_date/end_date.
        if "start_date" in kwargs and "start" not in kwargs:
            kwargs["start"] = kwargs.pop("start_date")
        if "end_date" in kwargs and "end" not in kwargs:
            kwargs["end"] = kwargs.pop("end_date")
        return self._client.fetch_price_data(symbol, **kwargs)
    
    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current price with volume - delegates to client"""
        return self._client.fetch_current_price(symbol)
    
    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """Fetch symbol details - delegates to client"""
        return self._client.fetch_symbol_details(symbol)
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamentals - delegates to client"""
        return self._client.fetch_fundamentals(symbol)
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch news - delegates to client"""
        return self._client.fetch_news(symbol, limit)
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings - delegates to client"""
        return self._client.fetch_earnings(symbol)
    
    def fetch_technical_indicators(self, symbol: str, indicator_type: str = "SMA", **kwargs) -> Dict[str, Any]:
        """Fetch technical indicators - delegates to client"""
        return self._client.fetch_technical_indicators(symbol, indicator_type, **kwargs)
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        return self._client.fetch_industry_peers(symbol)

    def fetch_actions(self, symbol: str) -> List[Dict[str, Any]]:
        return self._client.fetch_actions(symbol)

    def fetch_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        return self._client.fetch_dividends(symbol)

    def fetch_splits(self, symbol: str) -> List[Dict[str, Any]]:
        return self._client.fetch_splits(symbol)

    def fetch_financial_statements(self, symbol: str, *, quarterly: bool = True) -> Dict[str, Any]:
        return self._client.fetch_financial_statements(symbol, quarterly=quarterly)
    
    def fetch_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        return self._client.fetch_earnings_calendar(symbols, start_date, end_date)

    def fetch_earnings_for_date(self, earnings_date: str, symbols: List[str] = None) -> List[Dict[str, Any]]:
        return self._client.fetch_earnings_for_date(earnings_date, symbols)
    
    def is_available(self) -> bool:
        """Check availability - delegates to client"""
        return self._client.is_available()

    def fetch_quarterly_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch quarterly earnings history - delegates to client"""
        return self._client.fetch_quarterly_earnings_history(symbol)

    def fetch_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch analyst recommendations - delegates to client (Finnhub fallback)"""
        return self._client.fetch_analyst_recommendations(symbol)
