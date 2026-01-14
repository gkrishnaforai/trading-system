"""
Massive.com (formerly Polygon.io) data source implementation
Industry Standard: Real-time and historical data from all major U.S. exchanges
"""
import logging
from typing import Dict, Any, Optional, List
import pandas as pd

from app.data_sources.base import BaseDataSource
from app.config import settings
from app.providers.massive.client import MassiveClient, MASSIVE_AVAILABLE

logger = logging.getLogger(__name__)

class MassiveSource(BaseDataSource):
    """Massive.com data source implementation
    
    Industry Standard: Provides real-time and historical data from all major U.S. exchanges
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.massive_api_key
        if not self.api_key:
            raise ValueError("Massive API key is required")

        if not MASSIVE_AVAILABLE:
            raise ImportError("Massive library not available")

        self._client = MassiveClient.from_settings(api_key=self.api_key)

    @property
    def name(self) -> str:
        return "massive"

    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        """Fetch historical price data"""
        return self._client.fetch_price_data(symbol, **kwargs)

    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current price - requires paid plan"""
        return self._client.fetch_current_price(symbol)

    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """Fetch symbol details using Massive Python client (FREE reference data)"""
        return self._client.fetch_symbol_details(symbol)

    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles using Massive Python client"""
        return self._client.fetch_news(symbol, limit=limit)

    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data"""
        # Use symbol details for basic fundamentals
        return self.fetch_symbol_details(symbol)

    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings data using Python client"""
        return self._client.fetch_earnings(symbol)

    def fetch_technical_indicators(self, symbol: str, days: int = 90) -> Dict[str, Any]:
        """Fetch technical indicators from Massive API"""
        return self._client.fetch_technical_indicators(symbol, days=days)

    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers"""
        try:
            details = self.fetch_symbol_details(symbol)
            return {
                "sector": details.get("sector"),
                "industry": details.get("industry"),
                "peers": []  # Would need additional API calls
            }
        except Exception as e:
            logger.error(f"Error fetching industry peers for {symbol} from Massive.com: {e}")
            return {"sector": None, "industry": None, "peers": []}

    def is_available(self) -> bool:
        return self._client.is_available()
