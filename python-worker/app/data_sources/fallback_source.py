"""
Fallback Data Source
Tries primary source (Yahoo Finance) first, falls back to Finnhub if primary fails
Industry Standard: Multi-source data fetching with automatic fallback
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd

from app.data_sources.base import BaseDataSource
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.data_sources.finnhub_source import FinnhubSource

logger = logging.getLogger(__name__)


class FallbackDataSource(BaseDataSource):
    """
    Composite data source with automatic fallback
    Tries primary source (Yahoo Finance) first, falls back to Finnhub if needed
    """
    
    def __init__(self):
        """Initialize fallback data source"""
        self.primary_source = YahooFinanceSource()
        self.fallback_source = FinnhubSource()
        self._use_fallback = self.fallback_source.is_available()
        
        if self._use_fallback:
            logger.info("✅ Finnhub fallback enabled")
        else:
            logger.info("⚠️ Finnhub fallback disabled (no API key)")
    
    @property
    def name(self) -> str:
        return "fallback"
    
    def is_available(self) -> bool:
        """Check if data source is available"""
        return self.primary_source.is_available() or (self._use_fallback and self.fallback_source.is_available())
    
    def fetch_price_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y"
    ) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV price data"""
        try:
            kwargs: Dict[str, Any] = {"period": period}
            if start_date and end_date:
                kwargs.update({"start": start_date, "end": end_date})
            return self.primary_source.fetch_price_data(symbol, **kwargs)
        except Exception as e:
            logger.warning(f"Primary source failed for price data for {symbol}: {e}")
            if self._use_fallback:
                logger.info(f"Attempting Finnhub fallback for price data for {symbol}")
                # Finnhub doesn't support price data, so we can't fallback
                # But we'll log it for visibility
                logger.warning(f"Finnhub doesn't support price data, cannot fallback for {symbol}")
            raise
    
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetch current/live price"""
        try:
            return self.primary_source.fetch_current_price(symbol)
        except Exception as e:
            logger.warning(f"Primary source failed for current price for {symbol}: {e}")
            if self._use_fallback:
                logger.info(f"Attempting Finnhub fallback for current price for {symbol}")
                # Try Finnhub quote endpoint
                try:
                    return self._fetch_finnhub_quote(symbol)
                except Exception as fallback_error:
                    logger.error(f"Finnhub fallback also failed for {symbol}: {fallback_error}")
            raise
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data"""
        try:
            result = self.primary_source.fetch_fundamentals(symbol)
            # Check if result is meaningful (not empty)
            if result and len(result) > 0:
                return result
            # If empty, try fallback
            raise ValueError("Empty fundamentals from primary source")
        except Exception as e:
            logger.warning(f"Primary source failed for fundamentals for {symbol}: {e}")
            if self._use_fallback:
                logger.info(f"Attempting Finnhub fallback for fundamentals for {symbol}")
                try:
                    return self._fetch_finnhub_fundamentals(symbol)
                except Exception as fallback_error:
                    logger.error(f"Finnhub fallback also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles"""
        try:
            result = self.primary_source.fetch_news(symbol, limit)
            # Check if result is meaningful
            if result and len(result) > 0:
                return result
            # If empty, try fallback
            raise ValueError("Empty news from primary source")
        except Exception as e:
            logger.warning(f"Primary source failed for news for {symbol}: {e}")
            if self._use_fallback:
                logger.info(f"Attempting Finnhub fallback for news for {symbol}")
                try:
                    return self._fetch_finnhub_news(symbol, limit)
                except Exception as fallback_error:
                    logger.error(f"Finnhub fallback also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings calendar and history"""
        try:
            result = self.primary_source.fetch_earnings(symbol)
            # Check if result is meaningful
            if result and len(result) > 0:
                return result
            # If empty, try fallback
            raise ValueError("Empty earnings from primary source")
        except Exception as e:
            logger.warning(f"Primary source failed for earnings for {symbol}: {e}")
            if self._use_fallback:
                logger.info(f"Attempting Finnhub fallback for earnings for {symbol}")
                try:
                    return self._fetch_finnhub_earnings(symbol)
                except Exception as fallback_error:
                    logger.error(f"Finnhub fallback also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers and sector data"""
        try:
            result = self.primary_source.fetch_industry_peers(symbol)
            # Check if result is meaningful
            if result and (result.get('peers') or result.get('sector') or result.get('industry')):
                return result
            # If empty, try fallback
            raise ValueError("Empty industry peers from primary source")
        except Exception as e:
            logger.warning(f"Primary source failed for industry peers for {symbol}: {e}")
            if self._use_fallback:
                logger.info(f"Attempting Finnhub fallback for industry peers for {symbol}")
                try:
                    return self._fetch_finnhub_peers(symbol)
                except Exception as fallback_error:
                    logger.error(f"Finnhub fallback also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    # Finnhub-specific fetch methods (delegate to provider-backed thin adapter)
    def _fetch_finnhub_quote(self, symbol: str) -> Optional[float]:
        """Fetch current price from Finnhub via thin adapter."""
        try:
            details = self.fallback_source.fetch_symbol_details(symbol)
            return float(details.get("current_price", 0)) if details and details.get("current_price") else None
        except Exception as e:
            logger.error(f"Finnhub quote fetch failed for {symbol}: {e}")
            raise

    def _fetch_finnhub_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamentals from Finnhub via thin adapter."""
        try:
            return self.fallback_source.fetch_fundamentals(symbol) or {}
        except Exception as e:
            logger.error(f"Finnhub fundamentals fetch failed for {symbol}: {e}")
            raise

    def _fetch_finnhub_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch news from Finnhub via thin adapter."""
        try:
            return self.fallback_source.fetch_news(symbol, limit) or []
        except Exception as e:
            logger.error(f"Finnhub news fetch failed for {symbol}: {e}")
            raise

    def _fetch_finnhub_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings from Finnhub via thin adapter."""
        try:
            return self.fallback_source.fetch_earnings(symbol) or []
        except Exception as e:
            logger.error(f"Finnhub earnings fetch failed for {symbol}: {e}")
            raise

    def _fetch_finnhub_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers from Finnhub via thin adapter."""
        try:
            return self.fallback_source.fetch_industry_peers(symbol) or {}
        except Exception as e:
            logger.error(f"Finnhub peers fetch failed for {symbol}: {e}")
            raise

