"""
Finnhub Data Source
Provides analyst ratings and recommendations
Industry Standard: Professional market data API
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import requests
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from app.data_sources.base import BaseDataSource
import os

logger = logging.getLogger(__name__)


class FinnhubSource(BaseDataSource):
    """
    Finnhub data source for analyst ratings
    Provides professional analyst recommendations and price targets
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize Finnhub data source
        
        Args:
            api_key: Finnhub API key (from env or parameter)
        """
        self.api_key = api_key or os.getenv('FINNHUB_API_KEY')
        if not self.api_key:
            logger.warning("Finnhub API key not configured. Analyst ratings will not be available.")
        self.base_url = "https://finnhub.io/api/v1"
    
    @property
    def name(self) -> str:
        return "finnhub"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def fetch_analyst_ratings(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Fetch analyst ratings and recommendations from Finnhub
        
        Args:
            symbol: Stock symbol
        
        Returns:
            List of analyst ratings
        """
        if not self.api_key:
            logger.warning(f"Finnhub API key not configured. Cannot fetch analyst ratings for {symbol}")
            return []
        
        try:
            url = f"{self.base_url}/stock/recommendation"
            params = {
                "symbol": symbol,
                "token": self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if not data or not isinstance(data, list):
                return []
            
            ratings = []
            for item in data:
                # Map Finnhub ratings to our format
                rating_map = {
                    "strongBuy": "strong_buy",
                    "buy": "buy",
                    "hold": "hold",
                    "sell": "sell",
                    "strongSell": "strong_sell"
                }
                
                rating = rating_map.get(item.get('rating', '').lower(), 'hold')
                
                ratings.append({
                    "analyst_name": item.get('firm', 'Unknown'),
                    "rating": rating,
                    "price_target": item.get('targetPrice'),
                    "rating_date": datetime.fromtimestamp(item.get('period', 0)).date().isoformat() if item.get('period') else None,
                    "source": "finnhub"
                })
            
            logger.info(f"✅ Fetched {len(ratings)} analyst ratings for {symbol}")
            return ratings
            
        except Exception as e:
            logger.error(f"Error fetching analyst ratings from Finnhub for {symbol}: {e}")
            return []
    
    def fetch_price_data(self, symbol: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, period: str = "1y") -> Optional[pd.DataFrame]:
        """Not implemented - use Yahoo Finance for price data"""
        raise NotImplementedError("Use Yahoo Finance for price data")
    
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Not implemented - use Yahoo Finance for current price"""
        raise NotImplementedError("Use Yahoo Finance for current price")
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Not implemented - use Yahoo Finance for fundamentals"""
        raise NotImplementedError("Use Yahoo Finance for fundamentals")
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Not implemented - use Yahoo Finance for news"""
        raise NotImplementedError("Use Yahoo Finance for news")
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Not implemented - use Yahoo Finance for earnings"""
        raise NotImplementedError("Use Yahoo Finance for earnings")
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Not implemented - use Yahoo Finance for industry peers"""
        raise NotImplementedError("Use Yahoo Finance for industry peers")
    
    def is_available(self) -> bool:
        """Check if Finnhub API is available"""
        return self.api_key is not None

