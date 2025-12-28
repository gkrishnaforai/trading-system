"""
Base Plugin Adapter Framework
DRY & SOLID: Centralized logging, exception handling, and plugin lifecycle management
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type, List
from functools import wraps
from datetime import datetime

from app.plugins.base import Plugin, PluginMetadata, PluginType
from app.observability.logging import get_logger


class PluginError(Exception):
    """Base exception for plugin-related errors"""
    pass


class PluginInitializationError(PluginError):
    """Plugin failed to initialize"""
    pass


class PluginAvailabilityError(PluginError):
    """Plugin is not available"""
    pass


def handle_plugin_errors(plugin_name: str = None):
    """Decorator for centralized plugin error handling"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            logger = get_logger(f"plugin.{plugin_name or getattr(self, '_plugin_name', 'unknown')}")
            start_time = datetime.now()
            
            try:
                logger.debug(f"Starting {func.__name__}")
                result = func(self, *args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                logger.debug(f"Completed {func.__name__} in {duration:.2f}s")
                return result
                
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                logger.error(f"Error in {func.__name__} after {duration:.2f}s: {str(e)}", exc_info=True)
                
                # Re-raise with context
                if plugin_name:
                    raise PluginError(f"Plugin '{plugin_name}' error in {func.__name__}: {str(e)}") from e
                else:
                    raise PluginError(f"Error in {func.__name__}: {str(e)}") from e
                    
        return wrapper
    return decorator


class BasePluginAdapter(ABC):
    """
    SOLID: Single responsibility for plugin lifecycle management
    DRY: Common functionality shared across all adapters
    """
    
    def __init__(self, wrapped_instance, plugin_name: str):
        self._wrapped = wrapped_instance
        self._plugin_name = plugin_name
        self._logger = get_logger(f"plugin.{plugin_name}")
        self._initialized = False
        self._config = {}
        
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata - must be implemented by each adapter"""
        pass
    
    @handle_plugin_errors()
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize plugin with centralized error handling and logging
        SOLID: Open for extension, closed for modification
        """
        if self._initialized:
            self._logger.warning("Plugin already initialized")
            return True
            
        self._config = config or {}
        
        try:
            self._logger.info(f"Initializing plugin '{self._plugin_name}'")
            
            # Check availability first
            if not self.is_available():
                raise PluginAvailabilityError(f"Plugin '{self._plugin_name}' is not available")
            
            # Initialize wrapped instance
            if hasattr(self._wrapped, 'initialize'):
                success = self._wrapped.initialize(config)
                if not success:
                    raise PluginInitializationError(f"Wrapped instance initialization failed")
            
            self._initialized = True
            self._logger.info(f"✅ Plugin '{self._plugin_name}' initialized successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"❌ Failed to initialize plugin '{self._plugin_name}': {str(e)}")
            raise PluginInitializationError(f"Plugin initialization failed: {str(e)}") from e
    
    @handle_plugin_errors()
    def is_available(self) -> bool:
        """
        Check plugin availability with error handling
        DRY: Centralized availability checking logic
        """
        try:
            if hasattr(self._wrapped, 'is_available'):
                return self._wrapped.is_available()
            
            # Default availability check - try to access the wrapped instance
            return self._wrapped is not None
            
        except Exception as e:
            self._logger.error(f"Error checking availability for '{self._plugin_name}': {str(e)}")
            return False
    
    @handle_plugin_errors()
    def cleanup(self) -> None:
        """
        Cleanup plugin resources with error handling
        SOLID: Single responsibility for cleanup
        """
        if not self._initialized:
            return
            
        try:
            self._logger.info(f"Cleaning up plugin '{self._plugin_name}'")
            
            if hasattr(self._wrapped, 'cleanup'):
                self._wrapped.cleanup()
            
            self._initialized = False
            self._logger.info(f"✅ Plugin '{self._plugin_name}' cleaned up successfully")
            
        except Exception as e:
            self._logger.error(f"Error during cleanup of '{self._plugin_name}': {str(e)}")
            # Don't raise - cleanup errors should not prevent shutdown
    
    def _validate_config(self, required_keys: List[str]) -> None:
        """
        DRY: Centralized configuration validation
        """
        missing_keys = [key for key in required_keys if key not in self._config]
        if missing_keys:
            raise PluginInitializationError(f"Missing required config keys: {missing_keys}")
    
    def _get_config_value(self, key: str, default: Any = None) -> Any:
        """
        DRY: Centralized config value retrieval with logging
        """
        value = self._config.get(key, default)
        self._logger.debug(f"Config '{key}': {value if 'password' not in key.lower() else '***'}")
        return value


class DataSourceAdapter(BasePluginAdapter):
    """
    SOLID: Single responsibility for data source adapters
    DRY: Common data source functionality
    """
    
    @handle_plugin_errors()
    def fetch_price_data(self, symbol: str, **kwargs) -> Optional[Any]:
        """Fetch price data with error handling"""
        if not self._initialized:
            raise PluginError("Plugin not initialized")
        
        if not hasattr(self._wrapped, 'fetch_price_data'):
            raise NotImplementedError("Wrapped instance does not support fetch_price_data")
        
        return self._wrapped.fetch_price_data(symbol, **kwargs)
    
    @handle_plugin_errors()
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetch current price with error handling"""
        if not self._initialized:
            raise PluginError("Plugin not initialized")
        
        if not hasattr(self._wrapped, 'fetch_current_price'):
            raise NotImplementedError("Wrapped instance does not support fetch_current_price")
        
        return self._wrapped.fetch_current_price(symbol)
    
    @handle_plugin_errors()
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamentals with error handling"""
        if not self._initialized:
            raise PluginError("Plugin not initialized")
        
        if not hasattr(self._wrapped, 'fetch_fundamentals'):
            raise NotImplementedError("Wrapped instance does not support fetch_fundamentals")
        
        return self._wrapped.fetch_fundamentals(symbol)
    
    @handle_plugin_errors()
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch news with error handling"""
        if not self._initialized:
            raise PluginError("Plugin not initialized")
        
        if not hasattr(self._wrapped, 'fetch_news'):
            raise NotImplementedError("Wrapped instance does not support fetch_news")
        
        return self._wrapped.fetch_news(symbol, limit)
    
    @handle_plugin_errors()
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings with error handling"""
        if not self._initialized:
            raise PluginError("Plugin not initialized")
        
        if not hasattr(self._wrapped, 'fetch_earnings'):
            raise NotImplementedError("Wrapped instance does not support fetch_earnings")
        
        return self._wrapped.fetch_earnings(symbol)
    
    @handle_plugin_errors()
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers with error handling"""
        if not self._initialized:
            raise PluginError("Plugin not initialized")
        
        if not hasattr(self._wrapped, 'fetch_industry_peers'):
            raise NotImplementedError("Wrapped instance does not support fetch_industry_peers")
        
        return self._wrapped.fetch_industry_peers(symbol)
