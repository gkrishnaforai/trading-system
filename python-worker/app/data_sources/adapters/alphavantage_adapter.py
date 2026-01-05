"""
Alpha Vantage Data Adapter
Implements adapter pattern for Alpha Vantage data source
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd

from .base_adapter import BaseDataSourceAdapter, AdapterInitializationError
from ..alphavantage_source import AlphaVantageSource, AlphaVantageConfig
from app.plugins.base import PluginMetadata, PluginType
from app.observability.tracing import trace_function
from app.observability.logging import get_logger

logger = get_logger("alphavantage_adapter")

class AlphaVantageAdapter(BaseDataSourceAdapter):
    """Alpha Vantage data adapter implementing standard interface"""
    
    def __init__(self, config: Optional[AlphaVantageConfig] = None):
        super().__init__("alphavantage")  # Initialize base adapter
        self._config = config
        self.last_error: Optional[str] = None
        self._metadata = {
            "source_name": "alphavantage",
            "supported_data_types": ["price_data", "technical_indicators", "fundamentals", "market_news", "symbol_details"],
            "rate_limit": "5 calls/minute",
            "historical_coverage": "20 years",
            "real_time_support": False
        }
    
    def _create_source(self) -> AlphaVantageSource:
        """Create the underlying data source"""
        return AlphaVantageSource(self._config)
    
    def get_metadata(self) -> PluginMetadata:
        """Get adapter metadata"""
        return PluginMetadata(
            name="alphavantage",
            version="2.0.0",
            description="Alpha Vantage financial data provider with rate limiting",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[],
            config_schema={
                "api_key": {"type": "string", "required": True, "description": "Alpha Vantage API key"},
                "timeout": {"type": "integer", "default": 30, "description": "Request timeout in seconds"},
                "rate_limit_calls": {"type": "integer", "default": 5, "description": "Rate limit calls per minute"}
            }
        )
    
    @property
    def source_name(self) -> str:
        return "alphavantage"
    
    def is_available(self) -> bool:
        """Check if adapter is available"""
        try:
            self._logger.debug(f"🔍 Checking Alpha Vantage adapter availability...")
            
            # Check if source has is_available property or method
            if hasattr(self.source, 'is_available'):
                self._logger.debug(f"✅ Source has is_available attribute")
                if callable(getattr(self.source, 'is_available')):
                    self._logger.debug(f"📞 Calling source.is_available() method...")
                    result = self.source.is_available()
                    self._logger.debug(f"📊 source.is_available() returned: {result}")
                    if not result:
                        self.last_error = getattr(self.source, "last_error", None) or "Alpha Vantage is not available"
                    else:
                        self.last_error = None
                    return result
                else:
                    # It's a property, not a method
                    self._logger.debug(f"🏠 Reading source.is_available property...")
                    result = self.source.is_available
                    self._logger.debug(f"📊 source.is_available property value: {result}")
                    if not result:
                        self.last_error = getattr(self.source, "last_error", None) or "Alpha Vantage is not available"
                    else:
                        self.last_error = None
                    return result
            else:
                self._logger.warning(f"⚠️ Source doesn't have is_available attribute")
                self.last_error = "Alpha Vantage source missing is_available"
                return self.source is not None
        except Exception as e:
            self._logger.error(f"Error checking availability: {type(e).__name__}: {str(e)}")
            self.last_error = f"Alpha Vantage availability check error: {type(e).__name__}: {str(e)}"
            return False
    
    def _check_availability(self) -> bool:
        """Check Alpha Vantage availability with proper error handling"""
        try:
            self._logger.debug(f"🔍 Checking Alpha Vantage source availability...")
            
            if not hasattr(self.source, 'is_available'):
                self._logger.error(f"❌ Source doesn't have is_available attribute")
                return False
            
            # Check if is_available is a property or method
            is_available_attr = getattr(self.source, 'is_available')
            
            if callable(is_available_attr):
                # It's a method, call it
                self._logger.debug(f"📞 is_available is a method, calling it...")
                result = is_available_attr()
                self._logger.debug(f"📊 is_available() returned: {result}")
                return result
            else:
                # It's a property, access it directly
                self._logger.debug(f"🏠 is_available is a property, accessing it...")
                result = is_available_attr
                self._logger.debug(f"📊 is_available property value: {result}")
                return result
                
        except Exception as e:
            self._logger.error(f"❌ Error checking Alpha Vantage availability: {type(e).__name__}: {str(e)}")
            import traceback
            self._logger.debug(f"Full availability check traceback: {traceback.format_exc()}")
            return False
    
    @trace_function("alphavantage_initialize")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize Alpha Vantage adapter with API key and rate limiting"""
        try:
            # Store config first
            self._config = config or {}
            
            self._logger.info(f"🔧 Initializing Alpha Vantage adapter with config keys: {list(self._config.keys())}")
            
            # Get required API key FIRST
            try:
                api_key = self._get_config_value("api_key")
                self._logger.info(f"🔑 API key found: {bool(api_key)} (length: {len(api_key) if api_key else 0})")
                
                if not api_key:
                    raise AdapterInitializationError("Alpha Vantage API key is required but not provided in config")
            except Exception as e:
                raise AdapterInitializationError(f"Failed to get API key from config: {type(e).__name__}: {str(e)}") from e
            
            # Create AlphaVantageConfig object
            try:
                av_config = AlphaVantageConfig(
                    api_key=api_key,
                    rate_limit_calls=self._get_config_value("rate_limit_calls", 5),
                    rate_limit_window=self._get_config_value("rate_limit_window", 60.0),
                    timeout=self._get_config_value("timeout", 30)
                )
                self._logger.info(f"⚙️  Created AlphaVantageConfig: rate_limit={av_config.rate_limit_calls}/{av_config.rate_limit_window}s, timeout={av_config.timeout}s")
            except Exception as e:
                raise AdapterInitializationError(f"Failed to create AlphaVantageConfig: {type(e).__name__}: {str(e)}") from e
            
            # Update source with config
            try:
                self._config = av_config
                if hasattr(self.source, 'config'):
                    self.source.config = av_config
                    self._logger.info(f"✅ Updated source config")
                else:
                    self._logger.warning(f"⚠️  Source doesn't have config attribute")
            except Exception as e:
                raise AdapterInitializationError(f"Failed to update source config: {type(e).__name__}: {str(e)}") from e
            
            # Test availability before full initialization
            try:
                self._logger.info(f"🔍 Testing Alpha Vantage availability...")
                available = self._check_availability()
                self._logger.info(f"📊 Availability check result: {available}")
                
                if not available:
                    raise AdapterInitializationError("Alpha Vantage API is not available - check API key and connectivity")
            except Exception as e:
                if "AdapterInitializationError" in str(type(e)):
                    raise  # Re-raise our own errors
                raise AdapterInitializationError(f"Availability check failed: {type(e).__name__}: {str(e)}") from e
            
            # Call base initialization (skip availability check since we already validated)
            try:
                # Mark as initialized without redundant availability check
                self._initialized = True
                self._logger.info(f"✅ Adapter {self._adapter_name} initialized successfully")
            except Exception as e:
                raise AdapterInitializationError(f"Base initialization failed: {type(e).__name__}: {str(e)}") from e
            
            self._logger.info(
                f"✅ Alpha Vantage adapter initialized successfully: "
                f"rate_limit={av_config.rate_limit_calls}/{av_config.rate_limit_window}s, "
                f"timeout={av_config.timeout}s"
            )
            
            return True
            
        except Exception as e:
            # Only wrap if it's not already our custom exception
            if isinstance(e, AdapterInitializationError):
                self._logger.error(f"❌ Alpha Vantage adapter initialization failed: {str(e)}")
                raise
            else:
                self._logger.error(f"❌ Alpha Vantage adapter initialization failed: {type(e).__name__}: {str(e)}")
                import traceback
                self._logger.debug(f"Full traceback: {traceback.format_exc()}")
                raise AdapterInitializationError(f"Alpha Vantage adapter initialization failed: {type(e).__name__}: {str(e)}") from e
    
    @trace_function("fetch_price_data")
    def fetch_price_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y",
        days: Optional[int] = None,
        data_type: str = "daily"  # "daily" or "intraday"
    ) -> Optional[pd.DataFrame]:
        """
        Fetch price data from Alpha Vantage
        
        Args:
            symbol: Stock symbol
            start_date: Start date (not supported by Alpha Vantage API)
            end_date: End date (not supported by Alpha Vantage API)
            period: Period (compact=100 days, full=20+ years)
            days: Number of days (converted to appropriate period)
            data_type: "daily" for historical data, "intraday" for current data
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            if data_type == "intraday":
                # Fetch current intraday data (for 5-minute updates)
                return self._fetch_intraday_data(symbol, days)
            else:
                # Fetch historical daily data (one-time load)
                return self._fetch_daily_data(symbol, days)
                
        except Exception as e:
            self._logger.error(f"❌ Error fetching {data_type} price data for {symbol}: {type(e).__name__}: {str(e)}")
            import traceback
            self._logger.debug(f"Full traceback: {traceback.format_exc()}")
            return None
    
    def _fetch_daily_data(self, symbol: str, days: Optional[int] = None) -> Optional[pd.DataFrame]:
        """Fetch historical daily data"""
        try:
            # For free tier, always use compact (last 100 days)
            # Full data requires premium subscription
            outputsize = "compact"
            
            self._logger.info(f"📈 Fetching Alpha Vantage historical daily data for {symbol} (outputsize: {outputsize})")
            
            time_series_data = self.source.fetch_time_series_daily(
                symbol=symbol,
                outputsize=outputsize,
                datatype="json"
            )
            
            if time_series_data is None:
                return None
            
            df = self.source.convert_time_series_to_dataframe(time_series_data)
            
            # Filter by date range if specified (though Alpha Vantage doesn't support it well)
            if df is not None and hasattr(self, '_start_date') and hasattr(self, '_end_date'):
                df = df[(df.index.date >= self._start_date) & (df.index.date <= self._end_date)]
            
            self._logger.info(f"✅ Fetched {len(df) if df is not None else 0} daily price records for {symbol}")
            return df
            
        except Exception as e:
            self._logger.error(f"❌ Error fetching daily data for {symbol}: {type(e).__name__}: {str(e)}")
            raise
    
    def _fetch_intraday_data(self, symbol: str, days: Optional[int] = None) -> Optional[pd.DataFrame]:
        """Fetch current intraday data"""
        try:
            # For intraday data, we typically want the most recent data
            outputsize = "compact"  # Latest 100 data points
            
            self._logger.info(f"📊 Fetching Alpha Vantage intraday data for {symbol} (5min interval)")
            
            intraday_data = self.source.fetch_time_series_intraday(
                symbol=symbol,
                interval="5min",
                outputsize=outputsize,
                extended_hours=True,
                adjusted=True
            )
            
            if intraday_data is None:
                return None
            
            df = self.source.convert_intraday_to_dataframe(intraday_data, "5min")
            
            self._logger.info(f"✅ Fetched {len(df) if df is not None else 0} intraday price records for {symbol}")
            return df
            
        except Exception as e:
            self._logger.error(f"❌ Error fetching intraday data for {symbol}: {type(e).__name__}: {str(e)}")
            raise
    
    @trace_function("fetch_technical_indicators")
    def fetch_technical_indicators(
        self,
        symbol: str,
        indicators: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Fetch technical indicators from Alpha Vantage
        
        Args:
            symbol: Stock symbol
            indicators: List of indicators to fetch
            **kwargs: Additional parameters
        
        Returns:
            Dictionary with indicator data
        """
        try:
            if indicators is None:
                indicators = ["RSI", "MACD", "SMA", "EMA"]
            
            result = {}
            
            for indicator in indicators:
                try:
                    # Map indicator names to Alpha Vantage functions
                    function_map = {
                        "RSI": "RSI",
                        "MACD": "MACD", 
                        "SMA": "SMA",
                        "EMA": "EMA",
                        "BB": "BBANDS",
                        "STOCH": "STOCH",
                        "ADX": "ADX"
                    }
                    
                    function = function_map.get(indicator, indicator)
                    
                    # Default parameters
                    time_period = kwargs.get("time_period", 14)
                    interval = kwargs.get("interval", "daily")
                    series_type = kwargs.get("series_type", "close")
                    
                    indicator_data = self.source.fetch_technical_indicators(
                        symbol=symbol,
                        function=function,
                        interval=interval,
                        time_period=time_period,
                        series_type=series_type
                    )
                    
                    if indicator_data:
                        result[indicator] = indicator_data
                        
                except Exception as e:
                    self._logger.error(f"Error fetching {indicator} for {symbol}: {e}")
                    continue
            
            return result
            
        except Exception as e:
            self._logger.error(f"Error fetching technical indicators for {symbol}: {e}")
            return {}
    
    @trace_function("fetch_fundamentals")
    def fetch_fundamentals(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch fundamentals data from Alpha Vantage
        
        Args:
            symbol: Stock symbol
            **kwargs: Additional parameters
        
        Returns:
            Dictionary with fundamentals data
        """
        try:
            result = {}
            
            # Company overview
            overview = self.source.fetch_company_overview(symbol)
            if overview:
                result["overview"] = overview
            
            # Financial statements
            income_statement = self.source.fetch_income_statement(symbol)
            if income_statement:
                result["income_statement"] = income_statement
            
            balance_sheet = self.source.fetch_balance_sheet(symbol)
            if balance_sheet:
                result["balance_sheet"] = balance_sheet
            
            cash_flow = self.source.fetch_cash_flow(symbol)
            if cash_flow:
                result["cash_flow"] = cash_flow
            
            # Earnings
            earnings = self.source.fetch_earnings(symbol)
            if earnings:
                result["earnings"] = earnings
            
            return result
            
        except Exception as e:
            self._logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return {}
    
    @trace_function("fetch_news")
    def fetch_news(
        self,
        symbol: str = None,
        limit: int = 10,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch news from Alpha Vantage
        
        Args:
            symbol: Stock symbol (optional)
            limit: Number of articles to return
            **kwargs: Additional parameters
        
        Returns:
            List of news articles
        """
        try:
            tickers = symbol.upper() if symbol else None
            news_items = self.source.fetch_market_news(tickers=tickers)
            
            if news_items is None:
                return []
            
            # Limit results
            return news_items[:limit]
            
        except Exception as e:
            self._logger.error(f"Error fetching news: {e}")
            return []
    
    @trace_function("fetch_symbol_details")
    def fetch_symbol_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed symbol information"""
        try:
            overview = self.source.fetch_company_overview(symbol)
            
            if overview is None:
                return None
            
            # Extract key details
            details = {
                "symbol": overview.get("Symbol"),
                "name": overview.get("Name"),
                "sector": overview.get("Sector"),
                "industry": overview.get("Industry"),
                "market_cap": overview.get("MarketCapitalization"),
                "pe_ratio": overview.get("PERatio"),
                "pb_ratio": overview.get("PriceToBookRatio"),
                "dividend_yield": overview.get("DividendYield"),
                "eps": overview.get("EPS"),
                "beta": overview.get("Beta"),
                "description": overview.get("Description"),
                "country": overview.get("Country"),
                "currency": overview.get("Currency"),
                "exchange": overview.get("Exchange"),
                "data_source": "alphavantage"
            }
            
            return details
            
        except Exception as e:
            self._logger.error(f"Error fetching symbol details for {symbol}: {e}")
            return None
    
    @trace_function("fetch_earnings_calendar")
    def fetch_earnings_calendar(self, horizon: str = "3month", **kwargs):
        """Fetch earnings calendar from Alpha Vantage"""
        try:
            return self.source.fetch_earnings_calendar(horizon)
        except Exception as e:
            self._logger.error(f"Error fetching earnings calendar: {e}")
            return None
