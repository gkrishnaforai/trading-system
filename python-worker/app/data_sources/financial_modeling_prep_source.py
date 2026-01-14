"""
Financial Modeling Prep Data Source - Thin Adapter
Implements BaseDataSource by delegating to FinancialModelingPrepClient
Follows clean architecture pattern
"""
import logging
from typing import Dict, Any, Optional, List
import pandas as pd

from app.data_sources.base import BaseDataSource
from app.providers.financial_modeling_prep.client import FinancialModelingPrepClient, FinancialModelingPrepConfig
from app.observability.logging import get_logger

logger = get_logger("fmp_source")


class FinancialModelingPrepSource(BaseDataSource):
    """
    Financial Modeling Prep data source - thin adapter
    Delegates all operations to FinancialModelingPrepClient
    """
    
    def __init__(self, config: Optional[FinancialModelingPrepConfig] = None):
        if config is None:
            # Create client from settings
            self._client = FinancialModelingPrepClient.from_settings()
        else:
            self._client = FinancialModelingPrepClient(config)
        
        logger.info("✅ FMP Source initialized as thin adapter")
    
    @property
    def name(self) -> str:
        return "fmp"
    
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
    
    def fetch_enhanced_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch enhanced fundamentals - delegates to client"""
        return self._client.fetch_enhanced_fundamentals(symbol)
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch news - delegates to client"""
        return self._client.fetch_news(symbol, limit)
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings - delegates to client"""
        return self._client.fetch_earnings(symbol)
    
    def fetch_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """Fetch earnings calendar - delegates to client"""
        return self._client.fetch_earnings_calendar(symbols, start_date, end_date)
    
    def fetch_earnings_for_date(self, earnings_date: str, symbols: List[str] = None) -> List[Dict[str, Any]]:
        """Fetch earnings for date - delegates to client"""
        return self._client.fetch_earnings_for_date(earnings_date, symbols)
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers - delegates to client"""
        return self._client.fetch_industry_peers(symbol)
    
    def fetch_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch corporate actions - delegates to client"""
        return self._client.fetch_actions(symbol)
    
    def fetch_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch dividends - delegates to client"""
        return self._client.fetch_dividends(symbol)
    
    def fetch_splits(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch stock splits - delegates to client"""
        return self._client.fetch_splits(symbol)
    
    def fetch_financial_statements(self, symbol: str, *, quarterly: bool = True) -> Dict[str, Any]:
        """Fetch financial statements - delegates to client"""
        return self._client.fetch_financial_statements(symbol, quarterly=quarterly)
    
    def fetch_quarterly_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch quarterly earnings history - delegates to client"""
        return self._client.fetch_quarterly_earnings_history(symbol)
    
    def fetch_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch analyst recommendations - delegates to client"""
        return self._client.fetch_analyst_recommendations(symbol)
    
    def is_available(self) -> bool:
        """Check availability - delegates to client"""
        return self._client.is_available()
