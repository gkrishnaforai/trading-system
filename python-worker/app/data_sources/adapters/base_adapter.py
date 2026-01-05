"""
Base Data Source Adapter
SOLID: Single responsibility for adapter lifecycle
DRY: Common functionality shared across all adapters
Performance: Lazy loading, caching, connection pooling
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union, Callable
from functools import wraps
import time
from datetime import datetime

from app.plugins.base import DataSourcePlugin, PluginMetadata, PluginType
from app.observability.logging import get_logger
from app.observability.metrics import get_metrics
from app.observability.tracing import trace_function


class AdapterError(Exception):
    """Base adapter exception"""
    pass


class AdapterInitializationError(AdapterError):
    """Adapter failed to initialize"""
    pass


class AdapterUnavailableError(AdapterError):
    """Adapter is not available"""
    pass


class PerformanceMetrics:
    """Performance tracking for adapters"""
    
    def __init__(self, adapter_name: str):
        self.adapter_name = adapter_name
        self.metrics = get_metrics()
        self.logger = get_logger(f"adapter.{adapter_name}")
    
    def track_call(self, method_name: str):
        """Decorator to track method performance"""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    # Record metrics
                    self.metrics.histogram(
                        f"adapter_{self.adapter_name}_{method_name}_duration",
                        duration,
                        tags={"adapter": self.adapter_name, "method": method_name}
                    )
                    
                    self._logger.debug(
                        f"{method_name} completed in {duration:.3f}s",
                        extra={"duration": duration, "method": method_name}
                    )
                    
                    return result
                    
                except Exception as e:
                    duration = time.time() - start_time
                    self.metrics.increment(
                        f"adapter_{self.adapter_name}_{method_name}_errors",
                        tags={"adapter": self.adapter_name, "method": method_name, "error": type(e).__name__}
                    )
                    
                    self._logger.error(
                        f"{method_name} failed after {duration:.3f}s: {str(e)}",
                        extra={"duration": duration, "method": method_name, "error": str(e)}
                    )
                    
                    raise
                    
            return wrapper
        return decorator


class BaseDataSourceAdapter(DataSourcePlugin):
    """
    SOLID: Single responsibility for adapter lifecycle management
    DRY: Common functionality shared across all adapters
    Performance: Lazy loading, caching, metrics
    """
    
    def __init__(self, adapter_name: str):
        self._adapter_name = adapter_name
        self._source = None
        self._config = {}
        self._initialized = False
        self._availability_cache = {}
        self._metrics = PerformanceMetrics(adapter_name)
        self._logger = get_logger(f"adapter.{adapter_name}")
    
    @property
    def name(self) -> str:
        """Get adapter name for compatibility"""
        return self._adapter_name
    
    @property
    def source(self):
        """Lazy loading of data source"""
        if self._source is None:
            self._source = self._create_source()
            self._logger.debug(f"Created data source for {self._adapter_name}")
        return self._source
    
    @abstractmethod
    def _create_source(self):
        """Create the underlying data source - must be implemented by subclasses"""
        pass
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Get adapter metadata - must be implemented by subclasses"""
        pass
    
    @trace_function("adapter_initialize")
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Initialize adapter with validation and error handling
        Performance: Cached availability checks
        """
        if self._initialized:
            self._logger.warning(f"Adapter {self._adapter_name} already initialized")
            return True
        
        try:
            self._config = config or {}
            self._logger.info(f"Initializing adapter {self._adapter_name}")
            
            # Validate configuration
            self._validate_config()
            
            # Check availability with caching
            if not self._is_available_with_cache():
                raise AdapterUnavailableError(f"Adapter {self._adapter_name} is not available")
            
            # Initialize source if needed
            if hasattr(self.source, 'initialize'):
                success = self.source.initialize(config)
                if not success:
                    raise AdapterInitializationError(f"Source initialization failed for {self._adapter_name}")
            
            self._initialized = True
            self._logger.info(f"✅ Adapter {self._adapter_name} initialized successfully")
            
            # Record metrics
            self._metrics.metrics.increment(
                "adapter_initializations",
                labels={"adapter": self._adapter_name, "status": "success"}
            )
            
            return True
            
        except Exception as e:
            self._logger.error(f"❌ Failed to initialize adapter {self._adapter_name}: {str(e)}")
            
            # Record metrics
            self._metrics.metrics.increment(
                "adapter_initializations",
                labels={"adapter": self._adapter_name, "status": "error", "error": type(e).__name__}
            )
            
            # Re-raise with more context
            if isinstance(e, AdapterUnavailableError):
                raise AdapterInitializationError(f"Adapter initialization failed: {str(e)}") from e
            else:
                raise AdapterInitializationError(f"Adapter initialization failed: {str(e)}") from e
    
    @trace_function("adapter_is_available")
    def is_available(self) -> bool:
        """Check availability with caching for performance"""
        return self._is_available_with_cache()
    
    def _is_available_with_cache(self) -> bool:
        """Availability check with caching"""
        cache_key = f"availability_{self._adapter_name}"
        cache_time = 60  # Cache for 60 seconds
        
        current_time = time.time()
        if cache_key in self._availability_cache:
            cached_time, cached_value = self._availability_cache[cache_key]
            if current_time - cached_time < cache_time:
                return cached_value
        
        try:
            available = self._check_availability()
            self._availability_cache[cache_key] = (current_time, available)
            return available
            
        except Exception as e:
            self._logger.error(f"Error checking availability for {self._adapter_name}: {str(e)}")
            self._availability_cache[cache_key] = (current_time, False)
            return False
    
    def _check_availability(self) -> bool:
        """Actual availability check - can be overridden"""
        if hasattr(self.source, 'is_available'):
            return self.source.is_available()
        return self.source is not None
    
    @trace_function("adapter_cleanup")
    def cleanup(self) -> None:
        """Cleanup resources with error handling"""
        if not self._initialized:
            return
        
        try:
            self._logger.info(f"Cleaning up adapter {self._adapter_name}")
            
            if hasattr(self.source, 'cleanup'):
                self.source.cleanup()
            
            self._source = None
            self._initialized = False
            self._availability_cache.clear()
            
            self._logger.info(f"✅ Adapter {self._adapter_name} cleaned up successfully")
            
        except Exception as e:
            self._logger.error(f"Error during cleanup of {self._adapter_name}: {str(e)}")
    
    def _validate_config(self) -> None:
        """Validate configuration - can be overridden by subclasses"""
        pass
    
    def _get_config_value(self, key: str, default: Any = None) -> Any:
        """Get config value with logging"""
        value = self._config.get(key, default)
        
        # Mask sensitive values in logs
        log_value = value if 'password' not in key.lower() and 'key' not in key.lower() else '***'
        self._logger.debug(f"Config '{key}': {log_value}")
        
        return value
    
    # Performance-tracked data methods
    @trace_function("adapter_fetch_price_data")
    def fetch_price_data(self, symbol: str, **kwargs):
        """Fetch price data with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_price_data(symbol, **kwargs)
    
    @trace_function("adapter_fetch_current_price")
    def fetch_current_price(self, symbol: str):
        """Fetch current price with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_current_price(symbol)
    
    @trace_function("adapter_fetch_fundamentals")
    def fetch_fundamentals(self, symbol: str):
        """Fetch fundamentals with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_fundamentals(symbol)
    
    @trace_function("adapter_fetch_news")
    def fetch_news(self, symbol: str, limit: int = 10):
        """Fetch news with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_news(symbol, limit)
    
    @trace_function("adapter_fetch_earnings")
    def fetch_earnings(self, symbol: str):
        """Fetch earnings with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_earnings(symbol)
    
    @trace_function("adapter_fetch_industry_peers")
    def fetch_industry_peers(self, symbol: str):
        """Fetch industry peers with performance tracking"""
        if not self._initialized:
            raise AdapterError("Adapter not initialized")
        
        return self.source.fetch_industry_peers(symbol)
