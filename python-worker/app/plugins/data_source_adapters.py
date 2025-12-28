"""
Data Source Plugin Adapters
DRY & SOLID: Robust adapters with centralized logging, error handling, and lifecycle management
"""
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.plugins.base import DataSourcePlugin, PluginMetadata, PluginType
from app.plugins.base_adapter import DataSourceAdapter, handle_plugin_errors
from app.data_sources.massive_source import MassiveSource
from app.data_sources.yahoo_finance_source import YahooFinanceSource


class MassivePluginAdapter(DataSourceAdapter):
    """
    SOLID: Single responsibility for Massive.com integration
    DRY: Inherits common functionality from base adapter
    Best Practices: Proper error handling, logging, dependencies, cleanup, versioning
    """
    
    def __init__(self):
        super().__init__(MassiveSource(), "massive")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="massive",
            version="1.0.0",
            description="Massive.com financial data provider plugin",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[],  # No plugin dependencies
            config_schema={
                "api_key": {"type": "string", "required": True, "description": "Massive.com API key"},
                "rate_limit_calls": {"type": "integer", "default": 4, "description": "Rate limit calls per window"},
                "rate_limit_window": {"type": "number", "default": 60.0, "description": "Rate limit window in seconds"}
            }
        )
    
    @handle_plugin_errors("massive")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        SOLID: Initialize with proper validation and error handling
        Best Practices: Configuration validation, dependency checking
        """
        # Validate required config
        super().initialize(config)
        
        # Check for required API key
        self._validate_config(["api_key"])
        
        # Set rate limits from config
        rate_calls = self._get_config_value("rate_limit_calls", 4)
        rate_window = self._get_config_value("rate_limit_window", 60.0)
        
        # Configure the wrapped source
        if hasattr(self._wrapped, 'rate_limit_calls'):
            self._wrapped.rate_limit_calls = rate_calls
        if hasattr(self._wrapped, 'rate_limit_window'):
            self._wrapped.rate_limit_window = rate_window
        
        self._logger.info(f"✅ Massive plugin initialized with rate limit: {rate_calls}/{rate_window}s")
        return True
    
    @handle_plugin_errors("massive")
    def is_available(self) -> bool:
        """
        Best Practices: Comprehensive availability checking
        """
        if not super().is_available():
            return False
        
        # Check if API key is configured
        api_key = self._get_config_value("api_key")
        if not api_key:
            self._logger.warning("Massive API key not configured")
            return False
        
        # Check if the wrapped source is available
        try:
            return self._wrapped.is_available()
        except Exception as e:
            self._logger.error(f"Error checking Massive availability: {str(e)}")
            return False
    
    @handle_plugin_errors("massive")
    def cleanup(self) -> None:
        """
        Best Practices: Proper resource cleanup
        """
        super().cleanup()
        
        # Additional Massive-specific cleanup if needed
        if hasattr(self._wrapped, 'cleanup'):
            self._wrapped.cleanup()


class YahooFinancePluginAdapter(DataSourceAdapter):
    """
    SOLID: Single responsibility for Yahoo Finance integration
    DRY: Inherits common functionality from base adapter
    Best Practices: Free data source with proper error handling
    """
    
    def __init__(self):
        super().__init__(YahooFinanceSource(), "yahoo_finance")
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="yahoo_finance",
            version="1.0.0",
            description="Yahoo Finance free data provider plugin",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=[],  # No plugin dependencies
            config_schema={
                "timeout": {"type": "integer", "default": 30, "description": "Request timeout in seconds"},
                "retry_count": {"type": "integer", "default": 3, "description": "Number of retries on failure"}
            }
        )
    
    @handle_plugin_errors("yahoo_finance")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        SOLID: Initialize with proper configuration
        Best Practices: Configuration validation for optional parameters
        """
        super().initialize(config)
        
        # Set timeout and retry settings
        timeout = self._get_config_value("timeout", 30)
        retry_count = self._get_config_value("retry_count", 3)
        
        # Configure the wrapped source if it supports these settings
        if hasattr(self._wrapped, 'timeout'):
            self._wrapped.timeout = timeout
        if hasattr(self._wrapped, 'retry_count'):
            self._wrapped.retry_count = retry_count
        
        self._logger.info(f"✅ Yahoo Finance plugin initialized (timeout: {timeout}s, retries: {retry_count})")
        return True
    
    @handle_plugin_errors("yahoo_finance")
    def is_available(self) -> bool:
        """
        Best Practices: Check Yahoo Finance service availability
        """
        if not super().is_available():
            return False
        
        try:
            return self._wrapped.is_available()
        except Exception as e:
            self._logger.error(f"Error checking Yahoo Finance availability: {str(e)}")
            return False


class FallbackPluginAdapter(DataSourceAdapter):
    """
    SOLID: Single responsibility for fallback data source
    DRY: Inherits common functionality from base adapter
    Best Practices: Graceful degradation when primary sources fail
    """
    
    def __init__(self):
        # Fallback source would typically be a composite or cache
        super().__init__(None, "fallback")
        self._primary_adapters = []
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="fallback",
            version="1.0.0",
            description="Fallback data source plugin for graceful degradation",
            author="Trading System",
            plugin_type=PluginType.DATA_SOURCE,
            dependencies=["yahoo_finance"],  # Depends on Yahoo Finance as fallback
            config_schema={
                "cache_enabled": {"type": "boolean", "default": True, "description": "Enable cached data fallback"},
                "cache_ttl": {"type": "integer", "default": 3600, "description": "Cache TTL in seconds"}
            }
        )
    
    @handle_plugin_errors("fallback")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        SOLID: Initialize fallback with dependency checking
        Best Practices: Dependency validation
        """
        super().initialize(config)
        
        # Check if dependencies are available
        from app.plugins.registry import get_registry
        registry = get_registry()
        
        for dep in self.get_metadata().dependencies:
            if not registry.get(dep):
                self._logger.error(f"Dependency '{dep}' not available for fallback plugin")
                raise PluginInitializationError(f"Missing dependency: {dep}")
        
        self._logger.info("✅ Fallback plugin initialized with dependencies available")
        return True
    
    @handle_plugin_errors("fallback")
    def is_available(self) -> bool:
        """
        Best Practices: Check if any fallback options are available
        """
        if not super().is_available():
            return False
        
        # Check if cache is enabled and available
        cache_enabled = self._get_config_value("cache_enabled", True)
        if cache_enabled:
            return True
        
        # Check if dependencies are available
        from app.plugins.registry import get_registry
        registry = get_registry()
        
        for dep in self.get_metadata().dependencies:
            plugin = registry.get(dep)
            if plugin and plugin.is_available():
                return True
        
        return False
    
    @handle_plugin_errors("fallback")
    def fetch_price_data(self, symbol: str, **kwargs) -> Optional[Any]:
        """
        Best Practices: Try multiple sources in order of preference
        """
        # Try cache first if enabled
        cache_enabled = self._get_config_value("cache_enabled", True)
        if cache_enabled:
            # Implementation would check cache here
            pass
        
        # Try dependencies in order
        from app.plugins.registry import get_registry
        registry = get_registry()
        
        for dep in self.get_metadata().dependencies:
            plugin = registry.get(dep)
            if plugin and plugin.is_available():
                try:
                    return plugin.fetch_price_data(symbol, **kwargs)
                except Exception as e:
                    self._logger.warning(f"Fallback to {dep} failed for {symbol}: {str(e)}")
                    continue
        
        self._logger.error(f"All fallback sources failed for {symbol}")
        return None


# Plugin factory for easy registration
def create_data_source_adapters() -> List[DataSourceAdapter]:
    """
    DRY: Centralized adapter creation using new architecture
    SOLID: Single responsibility for adapter instantiation
    Performance: Uses optimized factory pattern
    """
    from app.data_sources.adapters import create_all_adapters
    
    # Create adapters using the new factory
    adapter_instances = create_all_adapters()
    
    # Convert to list for compatibility
    return list(adapter_instances.values())
