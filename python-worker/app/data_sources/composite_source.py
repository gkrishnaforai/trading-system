"""
Composite Data Source with Primary/Fallback Pattern
Industry Standard: Tries primary source first, automatically falls back to fallback on failure
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd

from app.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)


class CompositeDataSource(BaseDataSource):
    """
    Composite data source with automatic fallback
    Industry Standard: Primary source with automatic failover to fallback
    
    Pattern:
    1. Try primary source
    2. If primary fails or returns empty, try fallback
    3. Log all fallback attempts for monitoring
    """
    
    def __init__(self, primary: BaseDataSource, fallback: Optional[BaseDataSource] = None):
        """Initialize composite data source
        
        Args:
            primary: Primary data source to use first
            fallback: Fallback data source if primary fails
        """
        self.primary_source = primary
        self.fallback_source = fallback
        self._use_fallback = fallback is not None and fallback.is_available() if hasattr(fallback, 'is_available') else fallback is not None
        
        logger.info(
            f"Initialized CompositeDataSource: primary={primary.name}, "
            f"fallback={fallback.name if fallback else 'None'}"
        )
    
    @property
    def name(self) -> str:
        """Return composite name showing primary and fallback"""
        if self.fallback_source:
            return f"{self.primary_source.name}+{self.fallback_source.name}"
        return self.primary_source.name
    
    def is_available(self) -> bool:
        """Check if at least one source is available"""
        primary_available = self.primary_source.is_available() if hasattr(self.primary_source, 'is_available') else True
        fallback_available = (
            self.fallback_source.is_available() 
            if self.fallback_source and hasattr(self.fallback_source, 'is_available') 
            else False
        )
        return primary_available or fallback_available
    
    def fetch_price_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y",
        interval: str = "1d"
    ) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV price data with automatic fallback"""
        kwargs: Dict[str, Any] = {"period": period, "interval": interval}
        if start_date is not None:
            kwargs["start_date"] = start_date
        if end_date is not None:
            kwargs["end_date"] = end_date

        try:
            # Call with kwargs to support both positional-signature sources and **kwargs sources/adapters.
            result = self.primary_source.fetch_price_data(symbol, **kwargs)
            if result is not None and not result.empty:
                logger.debug(f"✅ Fetched price data from primary ({self.primary_source.name}) for {symbol}")
                return result
            # Empty result, try fallback
            raise ValueError("Empty price data from primary source")
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for price data for {symbol}: {e}")
            if self._use_fallback and self.fallback_source:
                logger.info(f"Attempting fallback ({self.fallback_source.name}) for price data for {symbol}")
                try:
                    result = self.fallback_source.fetch_price_data(symbol, **kwargs)
                    if result is not None and not result.empty:
                        logger.info(f"✅ Fetched price data from fallback ({self.fallback_source.name}) for {symbol}")
                        return result
                    raise ValueError("Empty price data from fallback source")
                except Exception as fallback_error:
                    logger.error(f"Fallback ({self.fallback_source.name}) also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch current/live price with automatic fallback"""
        try:
            result = self.primary_source.fetch_current_price(symbol)
            if result is not None:
                logger.debug(f"✅ Fetched current price from primary ({self.primary_source.name}) for {symbol}: ${result:.2f}")
                return result
            raise ValueError("No current price from primary source")
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for current price for {symbol}: {e}")
            if self._use_fallback and self.fallback_source:
                logger.info(f"Attempting fallback ({self.fallback_source.name}) for current price for {symbol}")
                try:
                    result = self.fallback_source.fetch_current_price(symbol)
                    if result is not None:
                        logger.info(f"✅ Fetched current price from fallback ({self.fallback_source.name}) for {symbol}: ${result:.2f}")
                        return result
                    raise ValueError("No current price from fallback source")
                except Exception as fallback_error:
                    logger.error(f"Fallback ({self.fallback_source.name}) also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data with automatic fallback"""
        primary_result: Dict[str, Any] = {}
        fallback_result: Dict[str, Any] = {}

        try:
            primary_result = self.primary_source.fetch_fundamentals(symbol) or {}
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for fundamentals for {symbol}: {e}")
            primary_result = {}

        if self._use_fallback and self.fallback_source:
            try:
                fallback_result = self.fallback_source.fetch_fundamentals(symbol) or {}
            except Exception as e:
                logger.warning(f"Fallback ({self.fallback_source.name}) failed for fundamentals for {symbol}: {e}")
                fallback_result = {}

        if not primary_result and fallback_result:
            logger.info(f"✅ Fetched fundamentals from fallback ({self.fallback_source.name}) for {symbol}")
            return fallback_result

        if primary_result and not fallback_result:
            logger.debug(f"✅ Fetched fundamentals from primary ({self.primary_source.name}) for {symbol}")
            return primary_result

        if not primary_result and not fallback_result:
            raise ValueError("Empty fundamentals from primary and fallback sources")

        required_keys = {
            "pe_ratio",
            "pb_ratio",
            "price_to_sales",
            "debt_to_equity",
            "roe",
            "revenue_growth",
            "total_equity",
            "total_debt",
            "long_term_debt",
            "short_term_debt",
            "current_debt",
        }

        def _is_missing_value(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, str):
                return val.strip() == ""
            if isinstance(val, bool):
                return False
            if isinstance(val, (int, float)):
                return val == 0
            try:
                import pandas as _pd
                # Only treat scalar NaNs as missing. For Series/arrays, do not evaluate truthiness.
                if _pd.api.types.is_scalar(val) and _pd.isna(val):
                    return True
            except Exception:
                pass
            return False

        merged = dict(primary_result)
        for k, v in fallback_result.items():
            if k not in merged or _is_missing_value(merged.get(k)):
                merged[k] = v

        missing_required = [k for k in required_keys if _is_missing_value(merged.get(k))]
        if missing_required:
            logger.info(
                f"Merged fundamentals for {symbol} from primary ({self.primary_source.name}) "
                f"+ fallback ({self.fallback_source.name}); still missing: {', '.join(missing_required)}"
            )
        else:
            logger.info(
                f"✅ Merged fundamentals for {symbol} from primary ({self.primary_source.name}) "
                f"+ fallback ({self.fallback_source.name})"
            )

        return merged
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles with automatic fallback"""
        try:
            result = self.primary_source.fetch_news(symbol, limit)
            if result and len(result) > 0:
                logger.debug(f"✅ Fetched news from primary ({self.primary_source.name}) for {symbol}: {len(result)} articles")
                return result
            raise ValueError("Empty news from primary source")
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for news for {symbol}: {e}")
            if self._use_fallback and self.fallback_source:
                logger.info(f"Attempting fallback ({self.fallback_source.name}) for news for {symbol}")
                try:
                    result = self.fallback_source.fetch_news(symbol, limit)
                    if result and len(result) > 0:
                        logger.info(f"✅ Fetched news from fallback ({self.fallback_source.name}) for {symbol}: {len(result)} articles")
                        return result
                    raise ValueError("Empty news from fallback source")
                except Exception as fallback_error:
                    logger.error(f"Fallback ({self.fallback_source.name}) also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings calendar and history with automatic fallback"""
        try:
            result = self.primary_source.fetch_earnings(symbol)
            if result and len(result) > 0:
                logger.debug(f"✅ Fetched earnings from primary ({self.primary_source.name}) for {symbol}: {len(result)} records")
                return result
            raise ValueError("Empty earnings from primary source")
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for earnings for {symbol}: {e}")
            if self._use_fallback and self.fallback_source:
                logger.info(f"Attempting fallback ({self.fallback_source.name}) for earnings for {symbol}")
                try:
                    result = self.fallback_source.fetch_earnings(symbol)
                    if result and len(result) > 0:
                        logger.info(f"✅ Fetched earnings from fallback ({self.fallback_source.name}) for {symbol}: {len(result)} records")
                        return result
                    raise ValueError("Empty earnings from fallback source")
                except Exception as fallback_error:
                    logger.error(f"Fallback ({self.fallback_source.name}) also failed for {symbol}: {fallback_error}")
                    raise
            raise
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers and sector data with automatic fallback"""
        try:
            result = self.primary_source.fetch_industry_peers(symbol)
            if result and (result.get('peers') or result.get('sector') or result.get('industry')):
                logger.debug(f"✅ Fetched industry peers from primary ({self.primary_source.name}) for {symbol}")
                return result
            raise ValueError("Empty industry peers from primary source")
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for industry peers for {symbol}: {e}")
            if self._use_fallback and self.fallback_source:
                logger.info(f"Attempting fallback ({self.fallback_source.name}) for industry peers for {symbol}")
                try:
                    result = self.fallback_source.fetch_industry_peers(symbol)
                    if result and (result.get('peers') or result.get('sector') or result.get('industry')):
                        logger.info(f"✅ Fetched industry peers from fallback ({self.fallback_source.name}) for {symbol}")
                        return result
                    raise ValueError("Empty industry peers from fallback source")
                except Exception as fallback_error:
                    logger.error(f"Fallback ({self.fallback_source.name}) also failed for {symbol}: {fallback_error}")
                    raise
            raise

