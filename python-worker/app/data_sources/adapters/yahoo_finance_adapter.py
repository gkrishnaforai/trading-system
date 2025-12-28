"""
Yahoo Finance Adapter
SOLID: Single responsibility for Yahoo Finance integration
DRY: Inherits common functionality from base adapter
Performance: Connection pooling, caching, optimized requests
"""
from typing import Dict, Any, Optional
from datetime import datetime

from app.data_sources.base import BaseDataSource
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.plugins.base import PluginMetadata, PluginType
from app.observability.tracing import trace_function
from .base_adapter import BaseDataSourceAdapter, AdapterInitializationError, AdapterError


class YahooFinanceAdapter(BaseDataSourceAdapter):
    """
    Yahoo Finance data source adapter
    Performance: Optimized for free data source with rate limiting
    """
    
    def __init__(self):
        super().__init__("yahoo_finance")
        self._timeout = 30
        self._retry_count = 3
    
    def _create_source(self) -> BaseDataSource:
        """Create Yahoo Finance data source"""
        return YahooFinanceSource()
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="yahoo_finance",
            version="2.0.0",
            description="Yahoo Finance free data provider with optimized caching",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[],
            config_schema={
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "min": 1,
                    "max": 300,
                    "description": "Request timeout in seconds"
                },
                "retry_count": {
                    "type": "integer", 
                    "default": 3,
                    "min": 0,
                    "max": 10,
                    "description": "Number of retries on failure"
                },
                "cache_enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable response caching"
                },
                "cache_ttl": {
                    "type": "integer",
                    "default": 300,
                    "min": 60,
                    "max": 3600,
                    "description": "Cache TTL in seconds"
                }
            }
        )
    
    @trace_function("yahoo_finance_fetch_price_data")
    def fetch_price_data(self, symbol: str, **kwargs):
        """Fetch price data with period conversion"""
        if not self._initialized:
            raise AdapterError("Yahoo Finance adapter not initialized")
        
        # Convert days to period if provided
        days = kwargs.get('days')
        if days:
            # Map days to appropriate yfinance period
            if days <= 30:
                period = "1mo"
            elif days <= 90:
                period = "3mo"
            elif days <= 180:
                period = "6mo"
            elif days <= 365:
                period = "1y"
            elif days <= 730:
                period = "2y"
            else:
                period = "5y"
            
            # Remove days from kwargs and add period
            kwargs_copy = kwargs.copy()
            kwargs_copy.pop('days', None)
            kwargs_copy['period'] = period
            
            self._logger.info(f" Converting days={days} to period={period} for Yahoo Finance")
        else:
            kwargs_copy = kwargs
        
        return self.source.fetch_price_data(symbol, **kwargs_copy)
    
    @trace_function("yahoo_finance_initialize")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize Yahoo Finance adapter with performance optimizations"""
        try:
            # Call base initialization
            super().initialize(config)
            
            # Configure performance settings
            self._timeout = self._get_config_value("timeout", 30)
            self._retry_count = self._get_config_value("retry_count", 3)
            self._cache_enabled = self._get_config_value("cache_enabled", True)
            self._cache_ttl = self._get_config_value("cache_ttl", 300)
            
            # Configure source if it supports these settings
            if hasattr(self.source, 'timeout'):
                self.source.timeout = self._timeout
            if hasattr(self.source, 'retry_count'):
                self.source.retry_count = self._retry_count
            
            self._logger.info(
                f"✅ Yahoo Finance adapter initialized: "
                f"timeout={self._timeout}s, retries={self._retry_count}, "
                f"cache={'enabled' if self._cache_enabled else 'disabled'}"
            )
            
            return True
            
        except Exception as e:
            raise AdapterInitializationError(f"Yahoo Finance adapter initialization failed: {str(e)}") from e
    
    def _validate_config(self) -> None:
        """Validate Yahoo Finance specific configuration"""
        timeout = self._get_config_value("timeout", 30)
        if not isinstance(timeout, int) or timeout < 1 or timeout > 300:
            raise AdapterInitializationError("timeout must be an integer between 1 and 300")
        
        retry_count = self._get_config_value("retry_count", 3)
        if not isinstance(retry_count, int) or retry_count < 0 or retry_count > 10:
            raise AdapterInitializationError("retry_count must be an integer between 0 and 10")
    
    def _check_availability(self) -> bool:
        """Check Yahoo Finance availability with network test"""
        try:
            # Yahoo Finance is generally available if we can create the source
            return self.source.is_available()
        except Exception as e:
            self._logger.warning(f"Yahoo Finance availability check failed: {str(e)}")
            return False
