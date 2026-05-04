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
            logger.info(f"🔍 Fetching price data for {symbol} with kwargs: {kwargs}")
            result = self.primary_source.fetch_price_data(symbol, **kwargs)
            logger.info(f"📊 Primary source result for {symbol}: {type(result)} - Empty: {getattr(result, 'empty', 'N/A')}")
            if result is not None and not result.empty:
                logger.info(f"✅ Fetched {len(result)} price data rows from primary ({self.primary_source.name}) for {symbol}")
                return result
            # Empty result, try fallback
            logger.warning(f"⚠️ Empty price data from primary source for {symbol}")
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
                # Extract price value from result dict for logging
                price_value = result.get('price') if isinstance(result, dict) else result
                if isinstance(price_value, (int, float)):
                    logger.debug(f"✅ Fetched current price from primary ({self.primary_source.name}) for {symbol}: ${price_value:.2f}")
                else:
                    logger.debug(f"✅ Fetched current price from primary ({self.primary_source.name}) for {symbol}: {result}")
                return result
            raise ValueError("No current price from primary source")
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for current price for {symbol}: {e}")
            if self._use_fallback and self.fallback_source:
                logger.info(f"Attempting fallback ({self.fallback_source.name}) for current price for {symbol}")
                try:
                    result = self.fallback_source.fetch_current_price(symbol)
                    if result is not None:
                        # Extract price value from result dict for logging
                        price_value = result.get('price') if isinstance(result, dict) else result
                        if isinstance(price_value, (int, float)):
                            logger.info(f"✅ Fetched current price from fallback ({self.fallback_source.name}) for {symbol}: ${price_value:.2f}")
                        else:
                            logger.info(f"✅ Fetched current price from fallback ({self.fallback_source.name}) for {symbol}: {result}")
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
            if result:
                return result
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for industry peers for {symbol}: {e}")
        
        if self.fallback_source:
            try:
                result = self.fallback_source.fetch_industry_peers(symbol)
                if result:
                    logger.info(f"✅ Fetched industry peers from fallback ({self.fallback_source.name}) for {symbol}")
                    return result
            except Exception as e:
                logger.warning(f"Fallback ({self.fallback_source.name}) also failed for industry peers for {symbol}: {e}")
        
        raise
    
    def fetch_financial_statements(self, symbol: str, quarterly: bool = False, period: str = None) -> Dict[str, Any]:
        """Fetch financial statements with automatic fallback"""
        logger.info(f"🔄 Composite Source - Fetching financial statements for {symbol}")
        effective_period = period
        if effective_period is None and quarterly:
            effective_period = "quarter"

        logger.info(f"   - Period: {effective_period}")
        logger.info(f"   - Primary source: {self.primary_source.name}")
        logger.info(f"   - Fallback source: {self.fallback_source.name if self.fallback_source else 'None'}")
        
        try:
            logger.info(f"📡 Trying primary source: {self.primary_source.name}")
            result = self.primary_source.fetch_financial_statements(symbol, effective_period)
            
            logger.info(f"📊 Primary source result for {symbol}:")
            logger.info(f"   - Type: {type(result)}")
            logger.info(f"   - Is truthy: {bool(result)}")
            if isinstance(result, dict):
                logger.info(f"   - Keys: {list(result.keys())}")
                for key, value in result.items():
                    if isinstance(value, list):
                        logger.info(f"   - {key}: {len(value)} items")
                    else:
                        logger.info(f"   - {key}: {type(value)}")
            
            if result:
                logger.info(f"✅ Primary source succeeded for {symbol}")
                return result
            else:
                logger.warning(f"⚠️ Primary source returned empty/falsy result for {symbol}")
        except Exception as e:
            logger.error(f"❌ Primary source ({self.primary_source.name}) failed for financial statements for {symbol}: {e}")
            logger.exception(f"Primary source exception details for {symbol}:")
        
        if self.fallback_source:
            try:
                logger.info(f"🔄 Trying fallback source: {self.fallback_source.name}")
                result = self.fallback_source.fetch_financial_statements(symbol, effective_period)
                
                logger.info(f"📊 Fallback source result for {symbol}:")
                logger.info(f"   - Type: {type(result)}")
                logger.info(f"   - Is truthy: {bool(result)}")
                
                if result:
                    logger.info(f"✅ Fetched financial statements from fallback ({self.fallback_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Fallback source returned empty/falsy result for {symbol}")
            except Exception as e:
                logger.error(f"❌ Fallback ({self.fallback_source.name}) also failed for financial statements for {symbol}: {e}")
                logger.exception(f"Fallback source exception details for {symbol}:")
        
        logger.error(f"❌ All sources failed for financial statements for {symbol}")
        raise Exception(f"All sources failed to fetch financial statements for {symbol}")
    
    def fetch_technical_indicators(self, symbol: str, timeframe: str = "1day") -> Dict[str, List[Dict[str, Any]]]:
        """Fetch technical indicators with automatic fallback"""
        try:
            # Try primary source first
            if hasattr(self.primary_source, 'fetch_technical_indicators'):
                result = self.primary_source.fetch_technical_indicators(symbol, timeframe)
                if result:
                    logger.info(f"✅ Fetched technical indicators from primary ({self.primary_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Primary source returned empty technical indicators for {symbol}")
            else:
                logger.warning(f"⚠️ Primary source ({self.primary_source.name}) doesn't support technical indicators")
        except Exception as e:
            logger.error(f"❌ Primary source ({self.primary_source.name}) failed for technical indicators for {symbol}: {e}")
        
        # Try fallback source
        if self.fallback_source and hasattr(self.fallback_source, 'fetch_technical_indicators'):
            try:
                logger.warning(f"🔄 FALLBACK ACTIVATED: Using {self.fallback_source.name} for technical indicators for {symbol} (primary: {self.primary_source.name} failed)")
                result = self.fallback_source.fetch_technical_indicators(symbol, timeframe)
                if result:
                    logger.info(f"✅ Fetched technical indicators from fallback ({self.fallback_source.name}) for {symbol}")
                    # Add fallback flag to the result for audit tracking
                    result['_fallback_used'] = True
                    result['_fallback_source'] = self.fallback_source.name
                    result['_primary_source'] = self.primary_source.name
                    return result
                else:
                    logger.warning(f"⚠️ Fallback source returned empty technical indicators for {symbol}")
            except Exception as e:
                logger.error(f"❌ Fallback ({self.fallback_source.name}) also failed for technical indicators for {symbol}: {e}")
        elif self.fallback_source:
            logger.warning(f"⚠️ Fallback source ({self.fallback_source.name}) doesn't support technical indicators")
        
        # If neither source supports technical indicators, return empty dict
        logger.error(f"❌ All sources failed for technical indicators for {symbol}")
        return {}
    
    def fetch_ema_data(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Fetch EMA data with automatic fallback"""
        try:
            # Try primary source first
            if hasattr(self.primary_source, 'fetch_ema_data'):
                result = self.primary_source.fetch_ema_data(symbol, period_length, timeframe)
                if result:
                    logger.info(f"✅ Fetched EMA data from primary ({self.primary_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Primary source returned empty EMA data for {symbol}")
            else:
                logger.warning(f"⚠️ Primary source ({self.primary_source.name}) doesn't support EMA data")
        except Exception as e:
            logger.error(f"❌ Primary source ({self.primary_source.name}) failed for EMA data for {symbol}: {e}")
        
        # Try fallback source
        if self.fallback_source and hasattr(self.fallback_source, 'fetch_ema_data'):
            try:
                result = self.fallback_source.fetch_ema_data(symbol, period_length, timeframe)
                if result:
                    logger.info(f"✅ Fetched EMA data from fallback ({self.fallback_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Fallback source returned empty EMA data for {symbol}")
            except Exception as e:
                logger.error(f"❌ Fallback ({self.fallback_source.name}) also failed for EMA data for {symbol}: {e}")
        elif self.fallback_source:
            logger.warning(f"⚠️ Fallback source ({self.fallback_source.name}) doesn't support EMA data")
        
        logger.warning(f"⚠️ No source supports EMA data for {symbol}")
        return []
    
    def fetch_sma_data(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Fetch SMA data with automatic fallback"""
        try:
            # Try primary source first
            if hasattr(self.primary_source, 'fetch_sma_data'):
                result = self.primary_source.fetch_sma_data(symbol, period_length, timeframe)
                if result:
                    logger.info(f"✅ Fetched SMA data from primary ({self.primary_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Primary source returned empty SMA data for {symbol}")
            else:
                logger.warning(f"⚠️ Primary source ({self.primary_source.name}) doesn't support SMA data")
        except Exception as e:
            logger.error(f"❌ Primary source ({self.primary_source.name}) failed for SMA data for {symbol}: {e}")
        
        # Try fallback source
        if self.fallback_source and hasattr(self.fallback_source, 'fetch_sma_data'):
            try:
                result = self.fallback_source.fetch_sma_data(symbol, period_length, timeframe)
                if result:
                    logger.info(f"✅ Fetched SMA data from fallback ({self.fallback_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Fallback source returned empty SMA data for {symbol}")
            except Exception as e:
                logger.error(f"❌ Fallback ({self.fallback_source.name}) also failed for SMA data for {symbol}: {e}")
        elif self.fallback_source:
            logger.warning(f"⚠️ Fallback source ({self.fallback_source.name}) doesn't support SMA data")
        
        logger.warning(f"⚠️ No source supports SMA data for {symbol}")
        return []
    
    def fetch_rsi_data(self, symbol: str, period_length: int = 14, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Fetch RSI data with automatic fallback"""
        try:
            # Try primary source first
            if hasattr(self.primary_source, 'fetch_rsi_data'):
                result = self.primary_source.fetch_rsi_data(symbol, period_length, timeframe)
                if result:
                    logger.info(f"✅ Fetched RSI data from primary ({self.primary_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Primary source returned empty RSI data for {symbol}")
            else:
                logger.warning(f"⚠️ Primary source ({self.primary_source.name}) doesn't support RSI data")
        except Exception as e:
            logger.error(f"❌ Primary source ({self.primary_source.name}) failed for RSI data for {symbol}: {e}")
        
        # Try fallback source
        if self.fallback_source and hasattr(self.fallback_source, 'fetch_rsi_data'):
            try:
                result = self.fallback_source.fetch_rsi_data(symbol, period_length, timeframe)
                if result:
                    logger.info(f"✅ Fetched RSI data from fallback ({self.fallback_source.name}) for {symbol}")
                    return result
                else:
                    logger.warning(f"⚠️ Fallback source returned empty RSI data for {symbol}")
            except Exception as e:
                logger.error(f"❌ Fallback ({self.fallback_source.name}) also failed for RSI data for {symbol}: {e}")
        elif self.fallback_source:
            logger.warning(f"⚠️ Fallback source ({self.fallback_source.name}) doesn't support RSI data")
        
        logger.warning(f"⚠️ No source supports RSI data for {symbol}")
        return []
    
    def fetch_corporate_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch corporate actions with automatic fallback"""
        try:
            result = self.primary_source.fetch_corporate_actions(symbol)
            if result:
                logger.info(f"✅ Fetched corporate actions from primary ({self.primary_source.name}) for {symbol}")
                return result
        except Exception as e:
            logger.warning(f"Primary source ({self.primary_source.name}) failed for corporate actions for {symbol}: {e}")
        
        if self.fallback_source:
            try:
                result = self.fallback_source.fetch_corporate_actions(symbol)
                if result:
                    logger.info(f"✅ Fetched corporate actions from fallback ({self.fallback_source.name}) for {symbol}")
                    return result
            except Exception as e:
                logger.warning(f"Fallback ({self.fallback_source.name}) also failed for corporate actions for {symbol}: {e}")
        
        raise

