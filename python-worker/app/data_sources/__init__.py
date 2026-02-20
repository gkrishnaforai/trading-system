"""
Data source implementations - Refactored for DRY and Robustness
Supports multiple data providers with Strategy Pattern and Plugin System
Clean separation of concerns: configuration, validation, and instantiation
"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from app.data_sources.base import BaseDataSource
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.data_sources.financial_modeling_prep_source import FinancialModelingPrepSource
from app.data_sources.fallback_source import FallbackDataSource
from app.config import settings
from app.plugins import get_plugin_registry as get_registry
from app.plugins.base import PluginType
import logging

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """Enumeration of available data source types (actual providers)"""
    YAHOO_FINANCE = "yahoo_finance"
    FMP = "fmp"
    MASSIVE = "massive"


@dataclass
class DataSourceRequirement:
    """Requirements for a data source to be available"""
    library_available: bool = True
    api_key_required: bool = False
    api_key_setting: Optional[str] = None
    enabled_setting: Optional[str] = None
    placeholder_keys: List[str] = None
    
    def __post_init__(self):
        if self.placeholder_keys is None:
            self.placeholder_keys = []


# Source requirements configuration (only actual data providers)
SOURCE_REQUIREMENTS: Dict[str, DataSourceRequirement] = {
    DataSourceType.YAHOO_FINANCE.value: DataSourceRequirement(),
    DataSourceType.FMP.value: DataSourceRequirement(
        api_key_required=True,
        api_key_setting="fmp_api_key",
        placeholder_keys=["your_fmp_api_key_here", ""]
    ),
    DataSourceType.MASSIVE.value: DataSourceRequirement(
        library_available=False,  # Will be set dynamically
        api_key_required=True,
        api_key_setting="massive_api_key",
        enabled_setting="massive_enabled"
    ),
}


class DataSourceRegistry:
    """Centralized registry for data sources with validation and configuration"""
    
    def __init__(self):
        self._sources: Dict[str, type] = {}
        self._primary_source: Optional[str] = None
        self._fallback_source: Optional[str] = None
        self._initialize_registry()
        self._configure_sources()
    
    def _initialize_registry(self):
        """Initialize the data source registry with actual providers only"""
        # Core data providers (actual sources)
        self._sources = {
            DataSourceType.YAHOO_FINANCE.value: YahooFinanceSource,
            DataSourceType.FMP.value: FinancialModelingPrepSource,
        }
        
        # Try to add Massive.com if available
        self._try_add_massive()
        
        # Note: FallbackDataSource is a composite strategy, not a primary source
        # It's used internally by CompositeDataSource, not registered as a standalone source
    
    def _try_add_massive(self):
        """Try to add Massive.com source if dependencies are available"""
        try:
            from massive import RESTClient
            POLYGON_LIBRARY_AVAILABLE = True
        except ImportError:
            POLYGON_LIBRARY_AVAILABLE = False
        
        # Update requirements with library availability
        SOURCE_REQUIREMENTS[DataSourceType.MASSIVE.value].library_available = POLYGON_LIBRARY_AVAILABLE
        
        if POLYGON_LIBRARY_AVAILABLE:
            try:
                from app.data_sources.massive_source import MassiveSource
                self._sources[DataSourceType.MASSIVE.value] = MassiveSource
                logger.info("✅ Massive.com source registered successfully")
            except ImportError as e:
                logger.warning(f"MassiveSource import failed: {e}")
        else:
            if self._is_massive_configured():
                logger.warning(
                    "⚠️ Massive.com is configured but 'massive' library is not installed.\n"
                    "   System will continue without Massive.com data source.\n"
                    "   To enable Massive.com: pip install massive>=2.0.0 and rebuild container"
                )
    
    def _is_massive_configured(self) -> bool:
        """Check if Massive.com is configured in settings"""
        return (getattr(settings, 'massive_enabled', False) and 
                getattr(settings, 'massive_api_key', None))
    
    def _configure_sources(self):
        """Configure primary and fallback sources based on settings"""
        # Determine primary source with priority: PRIMARY > DEFAULT > fallback
        self._primary_source = self._determine_primary_source()
        self._fallback_source = self._determine_fallback_source()
        
        # Validate primary source availability
        self._validate_primary_source()
        
        logger.info(f"📊 Data sources configured: Primary={self._primary_source}, Fallback={self._fallback_source}")
    
    def _determine_primary_source(self) -> str:
        """Determine primary data source based on configuration"""
        candidates = [
            getattr(settings, "primary_data_provider", "fmp"),
            settings.default_data_provider,
            DataSourceType.YAHOO_FINANCE.value  # Default to Yahoo Finance if nothing else configured
        ]
        
        for candidate in candidates:
            if candidate and candidate in self._sources:
                return candidate
        
        # Last resort - Yahoo Finance is always available
        return DataSourceType.YAHOO_FINANCE.value
    
    def _determine_fallback_source(self) -> Optional[str]:
        """Determine fallback data source (actual provider)"""
        # Use configured fallback if available and different from primary
        if (settings.fallback_data_provider and 
            settings.fallback_data_provider in self._sources and
            settings.fallback_data_provider != self._primary_source):
            return settings.fallback_data_provider
        
        # Auto-select fallback: if primary is not Yahoo Finance, use Yahoo Finance
        if self._primary_source != DataSourceType.YAHOO_FINANCE.value:
            return DataSourceType.YAHOO_FINANCE.value
        
        # If primary is Yahoo Finance, try FMP as fallback, or None
        if DataSourceType.FMP.value in self._sources:
            return DataSourceType.FMP.value
        
        return None  # No fallback available
    
    def _validate_primary_source(self):
        """Validate that primary source meets all requirements"""
        if not self.is_source_available(self._primary_source):
            error_msg = self._get_availability_error(self._primary_source)
            if self._primary_source == DataSourceType.MASSIVE.value:
                raise ImportError(error_msg)
            else:
                raise RuntimeError(error_msg)
    
    def is_source_available(self, source_name: str) -> bool:
        """Check if a data source is available and meets requirements"""
        if source_name not in self._sources:
            return False
        
        req = SOURCE_REQUIREMENTS.get(source_name)
        if not req:
            return True
        
        # Check library availability
        if not req.library_available:
            return False
        
        # Check if enabled (for sources with enabled_setting)
        if req.enabled_setting and not getattr(settings, req.enabled_setting, False):
            return False
        
        # Check API key requirements
        if req.api_key_required:
            api_key = getattr(settings, req.api_key_setting, "") or ""
            api_key = api_key.strip()
            
            # Allow placeholder if configured as primary/default (with warning)
            if not api_key or api_key in req.placeholder_keys:
                if (source_name in [settings.primary_data_provider, settings.default_data_provider]):
                    logger.warning(
                        f"⚠️ {source_name.upper()} is configured as primary/default but API key is not set. "
                        f"Please set {req.api_key_setting.upper()} in .env"
                    )
                    return True
                return False
        
        return True
    
    def _get_availability_error(self, source_name: str) -> str:
        """Get detailed error message for source unavailability"""
        req = SOURCE_REQUIREMENTS.get(source_name)
        if not req:
            return f"Unknown data source: {source_name}"
        
        if not req.library_available:
            if source_name == DataSourceType.MASSIVE.value:
                return (
                    f"'massive' library not installed. Rebuild Docker container: "
                    f"docker-compose build python-worker && docker-compose up -d python-worker"
                )
            return f"Required library for {source_name} is not installed"
        
        if req.enabled_setting and not getattr(settings, req.enabled_setting, False):
            return f"{source_name} is not enabled. Set {req.enabled_setting.upper()}=true in .env"
        
        if req.api_key_required:
            api_key = getattr(settings, req.api_key_setting, "") or ""
            if not api_key.strip() or api_key.strip() in req.placeholder_keys:
                return f"{source_name} API key not configured. Set {req.api_key_setting.upper()} in .env"
        
        return f"{source_name} is not available for unknown reason"
    
    def get_source_config(self, source_name: str) -> Dict[str, Any]:
        """Get configuration for a specific data source"""
        configs = {
            DataSourceType.FMP.value: {
                "api_key": settings.fmp_api_key,
                "base_url": settings.fmp_base_url,
                "timeout": settings.fmp_timeout,
                "max_retries": settings.fmp_max_retries,
                "retry_delay": settings.fmp_retry_delay,
                "rate_limit_calls": settings.fmp_rate_limit_calls,
                "rate_limit_window": settings.fmp_rate_limit_window
            },
            DataSourceType.MASSIVE.value: {
                "api_key": settings.massive_api_key,
                "rate_limit_calls": settings.massive_rate_limit_calls,
                "rate_limit_window": settings.massive_rate_limit_window
            },
            DataSourceType.YAHOO_FINANCE.value: {
                "timeout": getattr(settings, 'yahoo_finance_timeout', 30),
                "retry_count": getattr(settings, 'yahoo_finance_retry_count', 3)
            }
        }
        return configs.get(source_name, {})
    
    def create_source_instance(self, source_name: str) -> BaseDataSource:
        """Create an instance of a data source"""
        if not self.is_source_available(source_name):
            raise ValueError(f"Data source '{source_name}' is not available")
        
        # Try plugin registry first
        registry = get_registry()
        plugin = registry.get(source_name)
        if plugin and plugin.get_metadata().plugin_type == PluginType.DATA_SOURCE:
            return plugin
        
        # Use legacy registry
        source_class = self._sources[source_name]
        
        # Special handling for Massive.com
        if source_name == DataSourceType.MASSIVE.value:
            return source_class(api_key=settings.massive_api_key)
        
        return source_class()
    
    @property
    def primary_source(self) -> Optional[str]:
        """Get the primary data source name"""
        return self._primary_source
    
    @property
    def fallback_source(self) -> Optional[str]:
        """Get the fallback data source name"""
        return self._fallback_source
    
    @property
    def available_sources(self) -> List[str]:
        """Get list of available data source names"""
        return list(self._sources.keys())


# Global registry instance
_registry = DataSourceRegistry()

# Expose legacy compatibility variables
PRIMARY_DATA_SOURCE = _registry.primary_source
FALLBACK_DATA_SOURCE = _registry.fallback_source
DEFAULT_DATA_SOURCE = PRIMARY_DATA_SOURCE
DATA_SOURCES = {name: _registry._sources[name] for name in _registry.available_sources}

# Legacy compatibility functions
def _is_source_available(source_name: str) -> bool:
    """Legacy compatibility wrapper"""
    return _registry.is_source_available(source_name)


def get_data_source(name: str = None, use_fallback: bool = True) -> BaseDataSource:
    """
    Factory function to get a data source instance
    Industry Standard: Returns primary source, with automatic fallback capability
    
    Args:
        name: Name of data source (defaults to PRIMARY_DATA_SOURCE from config)
        use_fallback: If True and name is None, returns a composite source with fallback
    
    Returns:
        Data source instance (primary source, or composite with fallback if use_fallback=True)
    """
    if name is None:
        name = PRIMARY_DATA_SOURCE
    
    # Try new adapter factory first
    try:
        from app.data_sources.adapters import create_adapter
        from app.data_sources.composite_source import CompositeDataSource
        
        adapter = create_adapter(name)
        if adapter:
            config = _registry.get_source_config(name)
            adapter.initialize(config)
            
            if adapter.is_available():
                # Create composite if fallback is requested and available
                if (use_fallback and name == PRIMARY_DATA_SOURCE and 
                    FALLBACK_DATA_SOURCE and FALLBACK_DATA_SOURCE != name):
                    fallback_source = get_data_source(name=FALLBACK_DATA_SOURCE, use_fallback=False)
                    return CompositeDataSource(primary=adapter, fallback=fallback_source)
                
                return adapter
    except Exception as e:
        logger.debug(f"Adapter factory failed for {name}: {e}")
    
    # Fall back to legacy sources
    if not _registry.is_source_available(name):
        error_msg = _registry._get_availability_error(name)
        if name == DataSourceType.MASSIVE.value:
            raise ImportError(error_msg)
        raise ValueError(error_msg)
    
    # Create composite if fallback is requested
    if (use_fallback and name == PRIMARY_DATA_SOURCE and 
        FALLBACK_DATA_SOURCE and FALLBACK_DATA_SOURCE != name):
        if (_registry.is_source_available(PRIMARY_DATA_SOURCE) and 
            _registry.is_source_available(FALLBACK_DATA_SOURCE)):
            return _create_composite_source(PRIMARY_DATA_SOURCE, FALLBACK_DATA_SOURCE)
        elif _registry.is_source_available(PRIMARY_DATA_SOURCE):
            return _registry.create_source_instance(PRIMARY_DATA_SOURCE)
        elif _registry.is_source_available(FALLBACK_DATA_SOURCE):
            return _registry.create_source_instance(FALLBACK_DATA_SOURCE)
    
    # Return direct source instance
    return _registry.create_source_instance(name)


def _create_composite_source(primary_name: str, fallback_name: str) -> BaseDataSource:
    """Create a composite data source with primary and fallback"""
    from app.data_sources.composite_source import CompositeDataSource
    
    primary = _registry.create_source_instance(primary_name)
    fallback = None
    
    if fallback_name and _registry.is_source_available(fallback_name):
        fallback = _registry.create_source_instance(fallback_name)
    else:
        logger.warning(f"Fallback source '{fallback_name}' is not available. Using primary only.")
    
    return CompositeDataSource(primary=primary, fallback=fallback)


def get_primary_source() -> BaseDataSource:
    """Get the configured primary data source (no fallback)"""
    return get_data_source(name=PRIMARY_DATA_SOURCE, use_fallback=False)


def get_fallback_source() -> Optional[BaseDataSource]:
    """Get the configured fallback data source"""
    if FALLBACK_DATA_SOURCE:
        return get_data_source(name=FALLBACK_DATA_SOURCE, use_fallback=False)
    return None
