"""
Base data source interface (Strategy Pattern)
Allows pluggable data providers (Yahoo Finance, Alpha Vantage, Polygon, etc.)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd


class BaseDataSource(ABC):
    """Abstract base class for all data sources"""
    
    @abstractmethod
    def fetch_price_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y",
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV price data"""
        pass
    
    @abstractmethod
    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current/live price with volume data
        Returns dict with 'price' and 'volume' keys, or None if unavailable"""
        pass
    
    @abstractmethod
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data (P/E, revenue, etc.)"""
        pass
    
    @abstractmethod
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles"""
        pass
    
    @abstractmethod
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings calendar and history"""
        pass
    
    @abstractmethod
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers and sector data
        
        Returns:
            Dictionary with keys: 'sector', 'industry', 'peers' (list of peer dicts)
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if data source is available/healthy"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the data source"""
        pass

