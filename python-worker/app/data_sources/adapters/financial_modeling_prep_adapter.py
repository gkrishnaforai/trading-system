"""
Financial Modeling Prep Data Adapter
Implements adapter pattern for FMP data source
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import pandas as pd

from .base_adapter import BaseDataSourceAdapter, AdapterInitializationError
from ..financial_modeling_prep_source import FinancialModelingPrepSource, FinancialModelingPrepConfig
from app.plugins.base import PluginMetadata, PluginType
from app.observability.tracing import trace_function
from app.observability.logging import get_logger

logger = get_logger("fmp_adapter")

class FinancialModelingPrepAdapter(BaseDataSourceAdapter):
    """FMP data adapter implementing standard interface"""
    
    def __init__(self, config: Optional[FinancialModelingPrepConfig] = None):
        super().__init__("fmp")  # Initialize base adapter
        self._config = config
        self.last_error: Optional[str] = None
        self._metadata = {
            "source_name": "fmp",
            "supported_data_types": ["price_data", "fundamentals", "market_news", "earnings", "analyst_recommendations"],
            "rate_limit": "60 calls/minute",
            "historical_coverage": "20+ years",
            "real_time_support": True
        }
    
    def _create_source(self) -> FinancialModelingPrepSource:
        """Create the underlying data source"""
        return FinancialModelingPrepSource(self._config)
    
    def get_metadata(self) -> PluginMetadata:
        """Get adapter metadata"""
        return PluginMetadata(
            name="fmp",
            version="1.0.0",
            description="Financial Modeling Prep financial data provider with comprehensive coverage",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[],
            config_schema={
                "api_key": {"type": "string", "required": True, "description": "FMP API key"},
                "base_url": {"type": "string", "default": "https://financialmodelingprep.com/stable", "description": "FMP base URL"},
                "timeout": {"type": "integer", "default": 30, "description": "Request timeout in seconds"},
                "max_retries": {"type": "integer", "default": 3, "description": "Max retries on failure"},
                "retry_delay": {"type": "float", "default": 1.0, "description": "Retry delay in seconds"},
                "rate_limit_calls": {"type": "integer", "default": 60, "description": "Rate limit calls per minute"},
                "rate_limit_window": {"type": "float", "default": 60.0, "description": "Rate limit window in seconds"}
            }
        )
    
    @property
    def source_name(self) -> str:
        return "fmp"
    
    def is_available(self) -> bool:
        """Check if adapter is available"""
        try:
            self._logger.debug(f"🔍 Checking FMP adapter availability...")
            
            # Check if source has is_available property or method
            if hasattr(self.source, 'is_available'):
                self._logger.debug(f"✅ Source has is_available attribute")
                if callable(getattr(self.source, 'is_available')):
                    self._logger.debug(f"📞 Calling source.is_available() method...")
                    result = self.source.is_available()
                    self._logger.debug(f"📊 source.is_available() returned: {result}")
                    if not result:
                        self.last_error = getattr(self.source, "last_error", None) or "FMP is not available"
                    else:
                        self.last_error = None
                    return result
                else:
                    # It's a property, not a method
                    self._logger.debug(f"🏠 Reading source.is_available property...")
                    result = self.source.is_available
                    self._logger.debug(f"📊 source.is_available property value: {result}")
                    if not result:
                        self.last_error = getattr(self.source, "last_error", None) or "FMP is not available"
                    else:
                        self.last_error = None
                    return result
            else:
                self._logger.warning(f"⚠️ Source doesn't have is_available attribute")
                self.last_error = "FMP source missing is_available"
                return self.source is not None
        except Exception as e:
            self._logger.error(f"Error checking availability: {type(e).__name__}: {str(e)}")
            self.last_error = f"FMP availability check error: {type(e).__name__}: {str(e)}"
            return False
    
    def _check_availability(self) -> bool:
        """Check FMP availability with proper error handling"""
        try:
            self._logger.debug(f"🔍 Checking FMP source availability...")
            
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
            self._logger.error(f"❌ Error checking FMP availability: {type(e).__name__}: {str(e)}")
            import traceback
            self._logger.debug(f"Full availability check traceback: {traceback.format_exc()}")
            return False
    
    @trace_function("fmp_initialize")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize FMP adapter with API key and rate limiting"""
        try:
            # Store config first
            self._config = config or {}
            
            self._logger.info(f"🔧 Initializing FMP adapter with config keys: {list(self._config.keys())}")
            
            # Get required API key - try config first, then fall back to settings
            try:
                api_key = self._get_config_value("api_key")
                if not api_key:
                    # Fall back to settings if config doesn't have api_key
                    from app.config import settings
                    api_key = settings.fmp_api_key
                    self._logger.info(f"🔑 Using API key from settings: {bool(api_key)} (length: {len(api_key) if api_key else 0})")
                
                if not api_key:
                    raise AdapterInitializationError("FMP API key is required but not provided in config or settings")
            except Exception as e:
                raise AdapterInitializationError(f"Failed to get API key from config: {type(e).__name__}: {str(e)}") from e
            
            # Create FinancialModelingPrepConfig object - use settings as fallback
            try:
                from app.config import settings
                
                fmp_config = FinancialModelingPrepConfig(
                    api_key=api_key,
                    base_url=self._get_config_value("base_url", settings.fmp_base_url),
                    timeout=self._get_config_value("timeout", settings.fmp_timeout),
                    max_retries=self._get_config_value("max_retries", settings.fmp_max_retries),
                    retry_delay=self._get_config_value("retry_delay", settings.fmp_retry_delay),
                    rate_limit_calls=self._get_config_value("rate_limit_calls", settings.fmp_rate_limit_calls),
                    rate_limit_window=self._get_config_value("rate_limit_window", settings.fmp_rate_limit_window)
                )
                self._logger.info(f"⚙️  Created FinancialModelingPrepConfig: rate_limit={fmp_config.rate_limit_calls}/{fmp_config.rate_limit_window}s, timeout={fmp_config.timeout}s")
            except Exception as e:
                raise AdapterInitializationError(f"Failed to create FinancialModelingPrepConfig: {type(e).__name__}: {str(e)}") from e
            
            # Update source with config
            try:
                self._config = fmp_config
                if hasattr(self.source, 'config'):
                    self.source.config = fmp_config
                    self._logger.info(f"✅ Updated source config")
                else:
                    self._logger.warning(f"⚠️  Source doesn't have config attribute")
            except Exception as e:
                raise AdapterInitializationError(f"Failed to update source config: {type(e).__name__}: {str(e)}") from e
            
            # Test availability before full initialization
            try:
                self._logger.info(f"🔍 Testing FMP availability...")
                available = self._check_availability()
                self._logger.info(f"📊 Availability check result: {available}")
                
                if not available:
                    raise AdapterInitializationError("FMP API is not available - check API key and connectivity")
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
                f"✅ FMP adapter initialized successfully: "
                f"rate_limit={fmp_config.rate_limit_calls}/{fmp_config.rate_limit_window}s, "
                f"timeout={fmp_config.timeout}s"
            )
            
            return True
            
        except Exception as e:
            # Only wrap if it's not already our custom exception
            if isinstance(e, AdapterInitializationError):
                self._logger.error(f"❌ FMP adapter initialization failed: {str(e)}")
                raise
            else:
                self._logger.error(f"❌ FMP adapter initialization failed: {type(e).__name__}: {str(e)}")
                import traceback
                self._logger.debug(f"Full traceback: {traceback.format_exc()}")
                raise AdapterInitializationError(f"FMP adapter initialization failed: {type(e).__name__}: {str(e)}") from e
    
    @trace_function("fetch_price_data")
    def fetch_price_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        period: str = "1y",
        days: Optional[int] = None,
        interval: str = "1d",
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """
        Fetch price data from FMP
        
        Args:
            symbol: Stock symbol
            start_date: Start date (not directly supported by FMP API)
            end_date: End date (not directly supported by FMP API)
            period: Period string (mapped to timeseries)
            days: Number of days (mapped to timeseries)
            interval: Data interval (1d, 15m)
            **kwargs: Additional parameters
        """
        if not self._initialized:
            raise AdapterInitializationError("FMP adapter not initialized")
        
        try:
            # Map period/days to timeseries parameter
            timeseries = 5000  # Default max
            if days:
                timeseries = min(days, 5000)
            elif period == "1mo":
                timeseries = 30
            elif period == "3mo":
                timeseries = 90
            elif period == "6mo":
                timeseries = 180
            elif period == "1y":
                timeseries = 365
            elif period == "2y":
                timeseries = 730
            elif period == "5y":
                timeseries = 1825
            
            return self.source.fetch_price_data(
                symbol=symbol,
                timeseries=timeseries,
                interval=interval,
                **kwargs
            )
        except Exception as e:
            self._logger.error(f"Error fetching price data for {symbol}: {e}")
            return pd.DataFrame()
    
    def _validate_config(self) -> None:
        """Validate FMP specific configuration"""
        api_key = self._get_config_value("api_key")
        if not api_key or not isinstance(api_key, str):
            raise AdapterInitializationError("api_key must be a non-empty string")
        
        timeout = self._get_config_value("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
            raise AdapterInitializationError("timeout must be an integer between 1 and 300")
        
        max_retries = self._get_config_value("max_retries", 3)
        if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
            raise AdapterInitializationError("max_retries must be an integer between 0 and 10")
        
        rate_limit_calls = self._get_config_value("rate_limit_calls", 60)
        if not isinstance(rate_limit_calls, int) or rate_limit_calls < 1 or rate_limit_calls > 1000:
            raise AdapterInitializationError("rate_limit_calls must be an integer between 1 and 1000")
    
    # Delegate all other methods to the source
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        return self.source.fetch_current_price(symbol)
    
    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        return self.source.fetch_symbol_details(symbol)
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        return self.source.fetch_fundamentals(symbol)
    
    def fetch_enhanced_fundamentals(self, symbol: str) -> Dict[str, Any]:
        return self.source.fetch_enhanced_fundamentals(symbol)
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.source.fetch_news(symbol, limit)
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        return self.source.fetch_earnings(symbol)
    
    def fetch_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        return self.source.fetch_earnings_calendar(symbols, start_date, end_date)
    
    def fetch_earnings_for_date(self, earnings_date: str, symbols: List[str] = None) -> List[Dict[str, Any]]:
        return self.source.fetch_earnings_for_date(earnings_date, symbols)
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        return self.source.fetch_industry_peers(symbol)
    
    def fetch_actions(self, symbol: str) -> List[Dict[str, Any]]:
        return self.source.fetch_actions(symbol)
    
    def fetch_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        return self.source.fetch_dividends(symbol)
    
    def fetch_splits(self, symbol: str) -> List[Dict[str, Any]]:
        return self.source.fetch_splits(symbol)
    
    def fetch_financial_statements(self, symbol: str, *, quarterly: bool = True) -> Dict[str, Any]:
        return self.source.fetch_financial_statements(symbol, quarterly=quarterly)
    
    def fetch_quarterly_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        return self.source.fetch_quarterly_earnings_history(symbol)
    
    def fetch_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        return self.source.fetch_analyst_recommendations(symbol)
