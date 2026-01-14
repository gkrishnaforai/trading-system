"""
Alpha Vantage Data Source - Thin Adapter
Implements BaseDataSource by delegating to AlphaVantageClient
Follows clean architecture pattern
"""
import logging
from typing import Dict, Any, Optional, List
import pandas as pd

from app.data_sources.base import BaseDataSource
from app.providers.alphavantage.client import AlphaVantageClient, AlphaVantageConfig
from app.observability.logging import get_logger

logger = get_logger("alphavantage_source")


class AlphaVantageSource(BaseDataSource):
    """
    Alpha Vantage data source - thin adapter
    Delegates all operations to AlphaVantageClient
    """
    
    def __init__(self, config: Optional[AlphaVantageConfig] = None):
        if config is None:
            # Create client from settings
            self._client = AlphaVantageClient.from_settings()
        else:
            self._client = AlphaVantageClient(config)
        
        logger.info("✅ Alpha Vantage Source initialized as thin adapter")
    
    @property
    def name(self) -> str:
        return "alphavantage"
    
    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        """Fetch historical price data - delegates to client"""
        return self._client.fetch_price_data(symbol, **kwargs)
    
    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current price - delegates to client"""
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
        """Fetch industry peers - delegates to client"""
        return self._client.fetch_industry_peers(symbol)
    
    def is_available(self) -> bool:
        """Check availability - delegates to client"""
        return self._client.is_available()

    @property
    def last_error(self) -> Optional[str]:
        return getattr(self._client, "last_error", None)
