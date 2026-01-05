"""
Adapter Factory
SOLID: Single responsibility for adapter creation and management
DRY: Centralized adapter instantiation
Performance: Lazy loading, singleton pattern, caching
"""
from typing import Dict, Type, List, Optional
import threading
from dataclasses import dataclass

from app.plugins.base import DataSourcePlugin
from app.observability.logging import get_logger
from app.observability.tracing import trace_function
from app.data_sources.adapters.base_adapter import BaseDataSourceAdapter
from .yahoo_finance_adapter import YahooFinanceAdapter
from .massive_adapter import MassiveAdapter
from .alphavantage_adapter import AlphaVantageAdapter
from .financial_modeling_prep_adapter import FinancialModelingPrepAdapter
from .fallback_adapter import FallbackAdapter


@dataclass
class AdapterConfig:
    """Configuration for adapter creation"""
    name: str
    adapter_class: Type[BaseDataSourceAdapter]
    enabled: bool = True
    priority: int = 100  # Lower number = higher priority
    dependencies: List[str] = None


class AdapterFactory:
    """
    Factory for creating and managing data source adapters
    Performance: Singleton pattern, lazy loading, caching
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._logger = get_logger("adapter_factory")
            self._adapters: Dict[str, AdapterConfig] = {}
            self._instances: Dict[str, BaseDataSourceAdapter] = {}
            self._register_default_adapters()
            self._initialized = True
            self._logger.info("✅ Adapter factory initialized")
    
    def _register_default_adapters(self) -> None:
        """Register default adapters with configuration"""
        default_adapters = [
            AdapterConfig("fmp", FinancialModelingPrepAdapter, priority=50),  # Higher priority than Yahoo
            AdapterConfig("yahoo_finance", YahooFinanceAdapter, priority=200),
            AdapterConfig("yahoo", YahooFinanceAdapter, priority=200),
        ]
        
        # Only register Massive if enabled and API key is available
        from app.config import settings
        if settings.massive_enabled and settings.massive_api_key and settings.massive_api_key.strip():
            default_adapters.append(AdapterConfig("massive", MassiveAdapter, priority=100))
            self._logger.info("✅ Massive adapter registered (enabled and API key available)")
        else:
            self._logger.info("⚠️ Massive adapter skipped (not enabled or no API key)")
        
        # Only register Alpha Vantage if API key is available
        if settings.alphavantage_api_key and settings.alphavantage_api_key.strip():
            default_adapters.append(AdapterConfig("alphavantage", AlphaVantageAdapter, priority=150))
            self._logger.info("✅ Alpha Vantage adapter registered (API key available)")
        else:
            self._logger.info("⚠️ Alpha Vantage adapter skipped (no API key configured)")
        
        # Only register FMP if API key is available
        if settings.fmp_api_key and settings.fmp_api_key.strip():
            self._logger.info("✅ FMP adapter registered (API key available)")
        else:
            # Remove FMP from default adapters if no API key
            default_adapters = [a for a in default_adapters if a.name != "fmp"]
            self._logger.info("⚠️ FMP adapter skipped (no API key configured)")
        
        for config in default_adapters:
            self.register_adapter(config)
    
    @trace_function("adapter_factory_register")
    def register_adapter(self, config: AdapterConfig) -> None:
        """Register an adapter configuration"""
        with self._lock:
            self._adapters[config.name] = config
            self._logger.debug(f"Registered adapter: {config.name} (priority: {config.priority})")
    
    @trace_function("adapter_factory_create")
    def create_adapter(self, name: str) -> Optional[BaseDataSourceAdapter]:
        """Create an adapter instance with proper configuration"""
        with self._lock:
            # Check if adapter is registered
            if name not in self._adapters:
                self._logger.error(f"Adapter '{name}' not registered")
                return None
            
            config = self._adapters[name]
            
            # Check if adapter is enabled
            if not config.enabled:
                self._logger.warning(f"Adapter '{name}' is disabled")
                return None
            
            try:
                # Create new instance
                adapter = config.adapter_class()
                
                # Initialize with proper configuration from settings
                from app.config import settings
                adapter_config = {}
                
                if name == "fmp":
                    adapter_config = {
                        "api_key": settings.fmp_api_key,
                        "base_url": settings.fmp_base_url,
                        "timeout": settings.fmp_timeout,
                        "max_retries": settings.fmp_max_retries,
                        "retry_delay": settings.fmp_retry_delay,
                        "rate_limit_calls": settings.fmp_rate_limit_calls,
                        "rate_limit_window": settings.fmp_rate_limit_window
                    }
                elif name == "massive":
                    adapter_config = {
                        "api_key": settings.massive_api_key,
                        "rate_limit_calls": settings.massive_rate_limit_calls,
                        "rate_limit_window": settings.massive_rate_limit_window
                    }
                elif name == "yahoo_finance":
                    adapter_config = {
                        "timeout": getattr(settings, 'yahoo_finance_timeout', 30),
                        "retry_count": getattr(settings, 'yahoo_finance_retry_count', 3)
                    }
                elif name == "fallback":
                    adapter_config = {
                        "cache_enabled": getattr(settings, 'fallback_cache_enabled', True),
                        "cache_ttl": getattr(settings, 'fallback_cache_ttl', 3600),
                        "primary_source": getattr(settings, 'fallback_primary_source', 'yahoo_finance')
                    }
                
                # Initialize the adapter with configuration
                if adapter.initialize(adapter_config):
                    self._instances[name] = adapter
                    self._logger.info(f"✅ Created and initialized adapter: {name}")
                    return adapter
                else:
                    self._logger.error(f"❌ Failed to initialize adapter: {name}")
                    return None
                
            except Exception as e:
                self._logger.error(f"❌ Failed to create adapter '{name}': {str(e)}")
                return None
    
    @trace_function("adapter_factory_create_all")
    def create_all_adapters(self) -> Dict[str, BaseDataSourceAdapter]:
        """Create all enabled adapters in priority order"""
        adapters = {}
        
        # Sort by priority (lower number = higher priority)
        sorted_configs = sorted(
            [config for config in self._adapters.values() if config.enabled],
            key=lambda x: x.priority
        )
        
        for config in sorted_configs:
            adapter = self.create_adapter(config.name)
            if adapter:
                adapters[config.name] = adapter
        
        self._logger.info(f"Created {len(adapters)} adapters: {list(adapters.keys())}")
        return adapters
    
    def get_adapter_config(self, name: str) -> Optional[AdapterConfig]:
        """Get adapter configuration"""
        return self._adapters.get(name)
    
    def list_adapters(self) -> List[str]:
        """List all registered adapter names"""
        return list(self._adapters.keys())
    
    def list_enabled_adapters(self) -> List[str]:
        """List enabled adapter names in priority order"""
        enabled = [config for config in self._adapters.values() if config.enabled]
        sorted_enabled = sorted(enabled, key=lambda x: x.priority)
        return [config.name for config in sorted_enabled]
    
    def enable_adapter(self, name: str) -> bool:
        """Enable an adapter"""
        if name in self._adapters:
            self._adapters[name].enabled = True
            self._logger.info(f"✅ Enabled adapter: {name}")
            return True
        return False
    
    def disable_adapter(self, name: str) -> bool:
        """Disable an adapter"""
        if name in self._adapters:
            self._adapters[name].enabled = False
            self._logger.info(f"🚫 Disabled adapter: {name}")
            return True
        return False
    
    @trace_function("adapter_factory_cleanup")
    def cleanup(self) -> None:
        """Cleanup all adapter instances"""
        with self._lock:
            for name, adapter in self._instances.items():
                try:
                    adapter.cleanup()
                    self._logger.debug(f"Cleaned up adapter: {name}")
                except Exception as e:
                    self._logger.error(f"Error cleaning up adapter '{name}': {str(e)}")
            
            self._instances.clear()
            self._logger.info("✅ All adapters cleaned up")


# Global factory instance
_factory: Optional[AdapterFactory] = None


def get_adapter_factory() -> AdapterFactory:
    """Get global adapter factory instance"""
    global _factory
    if _factory is None:
        _factory = AdapterFactory()
    return _factory


def create_adapter(name: str) -> Optional[BaseDataSourceAdapter]:
    """Convenience function to create an adapter"""
    factory = get_adapter_factory()
    return factory.create_adapter(name)


def create_all_adapters() -> Dict[str, BaseDataSourceAdapter]:
    """Convenience function to create all adapters"""
    factory = get_adapter_factory()
    return factory.create_all_adapters()
