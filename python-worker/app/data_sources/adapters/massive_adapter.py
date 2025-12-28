"""
Massive.com Adapter
SOLID: Single responsibility for Massive.com integration
DRY: Inherits common functionality from base adapter
Performance: Rate limiting, connection pooling, optimized API usage
"""
from typing import Dict, Any, Optional
from datetime import datetime

from app.data_sources.base import BaseDataSource
from app.data_sources.massive_source import MassiveSource
from app.plugins.base import PluginMetadata, PluginType
from app.observability.tracing import trace_function
from .base_adapter import BaseDataSourceAdapter, AdapterInitializationError, AdapterError


class MassiveAdapter(BaseDataSourceAdapter):
    """
    Massive.com data source adapter
    Performance: Optimized for premium data with rate limiting
    """
    
    def __init__(self):
        super().__init__("massive")
        self._rate_limit_calls = 4
        self._rate_limit_window = 60.0
        self._api_key = None
    
    def _create_source(self) -> BaseDataSource:
        """Create Massive data source"""
        return MassiveSource()
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="massive",
            version="2.0.0",
            description="Massive.com premium financial data provider with rate limiting",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[],
            config_schema={
                "api_key": {
                    "type": "string",
                    "required": True,
                    "description": "Massive.com API key"
                },
                "rate_limit_calls": {
                    "type": "integer",
                    "default": 4,
                    "min": 1,
                    "max": 100,
                    "description": "Rate limit calls per window"
                },
                "rate_limit_window": {
                    "type": "number",
                    "default": 60.0,
                    "min": 1.0,
                    "max": 3600.0,
                    "description": "Rate limit window in seconds"
                },
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "min": 1,
                    "max": 300,
                    "description": "Request timeout in seconds"
                }
            }
        )
    
    @trace_function("massive_initialize")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize Massive adapter with API key and rate limiting"""
        try:
            # Store config first
            self._config = config or {}
            
            # Get required API key FIRST
            self._api_key = self._get_config_value("api_key")
            if not self._api_key:
                raise AdapterInitializationError("Massive API key is required")
            
            # Configure source BEFORE calling super().initialize()
            if hasattr(self.source, 'api_key'):
                self.source.api_key = self._api_key
            
            # Call base initialization (which checks availability)
            super().initialize(config)
            
            # Configure rate limiting
            self._rate_limit_calls = self._get_config_value("rate_limit_calls", 4)
            self._rate_limit_window = self._get_config_value("rate_limit_window", 60.0)
            timeout = self._get_config_value("timeout", 30)
            
            if hasattr(self.source, 'rate_limit_calls'):
                self.source.rate_limit_calls = self._rate_limit_calls
            if hasattr(self.source, 'rate_limit_window'):
                self.source.rate_limit_window = self._rate_limit_window
            if hasattr(self.source, 'timeout'):
                self.source.timeout = timeout
            
            self._logger.info(
                f"✅ Massive adapter initialized: "
                f"rate_limit={self._rate_limit_calls}/{self._rate_limit_window}s, "
                f"timeout={timeout}s"
            )
            
            return True
            
        except Exception as e:
            raise AdapterInitializationError(f"Massive adapter initialization failed: {str(e)}") from e
    
    def _validate_config(self) -> None:
        """Validate Massive specific configuration"""
        api_key = self._get_config_value("api_key")
        if not api_key or not isinstance(api_key, str):
            raise AdapterInitializationError("Valid API key is required")
        
        rate_calls = self._get_config_value("rate_limit_calls", 4)
        if not isinstance(rate_calls, int) or rate_calls < 1 or rate_calls > 100:
            raise AdapterInitializationError("rate_limit_calls must be an integer between 1 and 100")
        
        rate_window = self._get_config_value("rate_limit_window", 60.0)
        if not isinstance(rate_window, (int, float)) or rate_window < 1.0 or rate_window > 3600.0:
            raise AdapterInitializationError("rate_limit_window must be a number between 1.0 and 3600.0")
    
    def _check_availability(self) -> bool:
        """Check Massive availability with API key validation"""
        try:
            # Check if API key is configured
            if not self._api_key:
                self._logger.error("Massive API key not configured")
                return False
            
            # Check source availability with better error handling
            try:
                return self.source.is_available()
            except Exception as api_error:
                # Check if it's a plan limitation error
                error_str = str(api_error).lower()
                if any(phrase in error_str for phrase in ["not authorized", "not entitled", "upgrade your plan", "pricing"]):
                    self._logger.error(f"Massive.com API plan limitation: {str(api_error)}")
                    self._logger.error("Upgrade your plan at https://polygon.io/pricing")
                    return False
                else:
                    self._logger.warning(f"Massive availability check failed: {str(api_error)}")
                    return False
        except Exception as e:
            self._logger.warning(f"Massive availability check failed: {str(e)}")
            return False
    
    @trace_function("adapter_fetch_symbol_details")
    def fetch_symbol_details(self, symbol: str, **kwargs):
        """Fetch symbol details with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_symbol_details(symbol)
    
    @trace_function("adapter_fetch_technical_indicators")
    def fetch_technical_indicators(self, symbol: str, days: int = 90, **kwargs):
        """Fetch technical indicators with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_technical_indicators(symbol, days)
    
    @trace_function("adapter_fetch_fundamentals")
    def fetch_fundamentals(self, symbol: str, **kwargs):
        """Fetch fundamentals with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_fundamentals(symbol)
