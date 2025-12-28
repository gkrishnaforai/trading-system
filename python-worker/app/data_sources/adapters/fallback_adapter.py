"""
Fallback Adapter
SOLID: Single responsibility for graceful degradation
DRY: Inherits common functionality from base adapter
Performance: Cached data, dependency management, fast failover
"""
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.data_sources.base import BaseDataSource
from app.plugins.base import PluginMetadata, PluginType
from app.observability.tracing import trace_function
from .base_adapter import BaseDataSourceAdapter, AdapterInitializationError


class FallbackAdapter(BaseDataSourceAdapter):
    """
    Fallback data source adapter for graceful degradation
    Performance: Uses cached data and dependency management
    """
    
    def __init__(self):
        super().__init__("fallback")
        self._cache_enabled = True
        self._cache_ttl = 3600
        self._dependencies = ["yahoo_finance"]
    
    def _create_source(self) -> BaseDataSource:
        """Fallback doesn't wrap a specific source - uses dependencies"""
        return None  # Fallback adapter doesn't have a direct source
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="fallback",
            version="2.0.0",
            description="Fallback data source with caching and dependency management",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=self._dependencies,
            config_schema={
                "cache_enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable cached data fallback"
                },
                "cache_ttl": {
                    "type": "integer",
                    "default": 3600,
                    "min": 300,
                    "max": 86400,
                    "description": "Cache TTL in seconds"
                },
                "primary_source": {
                    "type": "string",
                    "default": "yahoo_finance",
                    "description": "Primary fallback source"
                }
            }
        )
    
    @trace_function("fallback_initialize")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize fallback adapter with dependency checking"""
        try:
            # Call base initialization
            super().initialize(config)
            
            # Configure caching
            self._cache_enabled = self._get_config_value("cache_enabled", True)
            self._cache_ttl = self._get_config_value("cache_ttl", 3600)
            self._primary_source = self._get_config_value("primary_source", "yahoo_finance")
            
            # Check dependencies
            if not self._check_dependencies():
                raise AdapterInitializationError("Required dependencies not available")
            
            self._logger.info(
                f"✅ Fallback adapter initialized: "
                f"cache={'enabled' if self._cache_enabled else 'disabled'}, "
                f"primary_source={self._primary_source}"
            )
            
            return True
            
        except Exception as e:
            raise AdapterInitializationError(f"Fallback adapter initialization failed: {str(e)}") from e
    
    def _check_dependencies(self) -> bool:
        """Check if required dependencies are available"""
        from app.data_sources.adapters import create_adapter
        
        for dep in self._dependencies:
            try:
                adapter = create_adapter(dep)
                if not adapter or not adapter.is_available():
                    self._logger.error(f"Dependency '{dep}' not available for fallback adapter")
                    return False
            except Exception as e:
                self._logger.error(f"Error checking dependency '{dep}': {str(e)}")
                return False
        
        return True
    
    def _check_availability(self) -> bool:
        """Fallback is available if cache is enabled or dependencies are available"""
        if self._cache_enabled:
            return True
        
        return self._check_dependencies()
    
    @trace_function("fallback_fetch_price_data")
    def fetch_price_data(self, symbol: str, **kwargs):
        """Fetch price data using fallback strategy"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        # Try cache first if enabled
        if self._cache_enabled:
            cached_data = self._get_cached_data(f"price_data_{symbol}")
            if cached_data:
                self._logger.debug(f"Returning cached price data for {symbol}")
                return cached_data
        
        # Try dependencies in order
        return self._try_dependencies("fetch_price_data", symbol, **kwargs)
    
    @trace_function("fallback_fetch_current_price")
    def fetch_current_price(self, symbol: str):
        """Fetch current price using fallback strategy"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        # Try cache first
        if self._cache_enabled:
            cached_price = self._get_cached_data(f"current_price_{symbol}")
            if cached_price is not None:
                self._logger.debug(f"Returning cached current price for {symbol}")
                return cached_price
        
        # Try dependencies
        return self._try_dependencies("fetch_current_price", symbol)
    
    def _try_dependencies(self, method_name: str, *args, **kwargs):
        """Try dependencies in order of preference"""
        from app.data_sources.adapters import create_adapter
        
        for dep in self._dependencies:
            adapter = create_adapter(dep)
            if adapter and adapter.is_available():
                try:
                    method = getattr(adapter, method_name)
                    result = method(*args, **kwargs)
                    
                    # Cache successful result
                    if self._cache_enabled and result is not None:
                        cache_key = f"{method_name}_{args[0] if args else 'unknown'}"
                        self._cache_data(cache_key, result)
                    
                    self._logger.debug(f"Fallback to {dep} succeeded for {method_name}")
                    return result
                    
                except Exception as e:
                    self._logger.warning(f"Fallback to {dep} failed for {method_name}: {str(e)}")
                    continue
        
        self._logger.error(f"All fallback sources failed for {method_name}")
        return None
    
    def _get_cached_data(self, key: str):
        """Get cached data - implementation would depend on cache system"""
        # This would integrate with your caching system
        # For now, return None to indicate no cache
        return None
    
    def _cache_data(self, key: str, data):
        """Cache data - implementation would depend on cache system"""
        # This would integrate with your caching system
        pass
    
    # Implement other required methods with fallback strategy
    def fetch_fundamentals(self, symbol: str):
        return self._try_dependencies("fetch_fundamentals", symbol)
    
    def fetch_news(self, symbol: str, limit: int = 10):
        return self._try_dependencies("fetch_news", symbol, limit)
    
    def fetch_earnings(self, symbol: str):
        return self._try_dependencies("fetch_earnings", symbol)
    
    def fetch_industry_peers(self, symbol: str):
        return self._try_dependencies("fetch_industry_peers", symbol)
