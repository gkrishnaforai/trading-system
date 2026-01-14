"""
Data source implementations
Supports multiple data providers with Strategy Pattern and Plugin System
"""
from typing import Optional
from app.data_sources.base import BaseDataSource
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.data_sources.financial_modeling_prep_source import FinancialModelingPrepSource
from app.data_sources.fallback_source import FallbackDataSource
from app.config import settings
from app.plugins import get_plugin_registry as get_registry
from app.plugins.base import PluginType

# Try to import Massive.com source (optional)
# Check if massive library is available first
# Official Massive.com Python client: pip install -U massive
# Import: from massive import RESTClient
try:
    from massive import RESTClient
    POLYGON_LIBRARY_AVAILABLE = True
except ImportError:
    POLYGON_LIBRARY_AVAILABLE = False

# Now try to import MassiveSource
if POLYGON_LIBRARY_AVAILABLE:
    try:
        from app.data_sources.massive_source import MassiveSource
        MASSIVE_AVAILABLE = True
    except ImportError as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"MassiveSource import failed (massive library available but source import failed): {e}")
        MASSIVE_AVAILABLE = False
        MassiveSource = None
else:
    MASSIVE_AVAILABLE = False
    MassiveSource = None

# Legacy registry (for backward compatibility)
DATA_SOURCES = {
    "yahoo_finance": YahooFinanceSource,
    "fmp": FinancialModelingPrepSource,
    "fallback": FallbackDataSource,  # Fallback source with Yahoo Finance + Finnhub
}

# Add Massive.com if available
# Only add if: massive library is installed AND massive is enabled AND API key is set
if POLYGON_LIBRARY_AVAILABLE and MASSIVE_AVAILABLE and settings.massive_enabled and settings.massive_api_key:
    DATA_SOURCES["massive"] = MassiveSource
elif settings.massive_enabled and settings.massive_api_key and not POLYGON_LIBRARY_AVAILABLE:
    # Log warning but don't fail - allow system to work without massive
    import logging
    logger = logging.getLogger(__name__)
    warning_msg = (
        "⚠️  WARNING: Massive.com is enabled but 'massive' library is not installed.\n"
        "   System will continue without Massive.com data source.\n"
        "   To enable Massive.com: pip install massive>=2.0.0 and rebuild container"
    )
    logger.warning(warning_msg)
    # Don't raise ImportError - allow system to continue with other data sources

# Determine primary and fallback sources from config (Industry Standard pattern)
# Priority: primary_data_provider > default_data_provider > "fallback"
PRIMARY_DATA_SOURCE = None
FALLBACK_DATA_SOURCE = None

# Helper to check if a source is actually available
def _is_source_available(source_name: str) -> bool:
    """Check if a data source is available and can be instantiated"""
    if source_name not in DATA_SOURCES:
        return False
    if source_name == "massive":
        # Massive requires massive library AND API key
        return POLYGON_LIBRARY_AVAILABLE and MASSIVE_AVAILABLE and settings.massive_api_key is not None
    elif source_name == "fmp":
        # FMP requires API key
        return settings.fmp_api_key and settings.fmp_api_key.strip()
    return True

# Validate that required dependencies are installed if sources are configured
if settings.primary_data_provider == "massive" or settings.default_data_provider == "massive":
    if not POLYGON_LIBRARY_AVAILABLE:
        import logging
        logger = logging.getLogger(__name__)
        error_msg = (
            f"❌ CRITICAL: 'massive' library is not installed but Massive.com is configured as data provider.\n"
            f"   'massive>=2.0.0' is in requirements.txt but the Docker container needs to be rebuilt.\n"
            f"   Run: docker-compose build python-worker\n"
            f"   Then: docker-compose up -d python-worker"
        )
        logger.error(error_msg)
        raise ImportError(
            "massive library not installed. Rebuild Docker container: "
            "docker-compose build python-worker && docker-compose up -d python-worker"
        )

if settings.primary_data_provider:
    if settings.primary_data_provider in DATA_SOURCES:
        PRIMARY_DATA_SOURCE = settings.primary_data_provider
    else:
        raise ValueError(
            f"Primary data provider '{settings.primary_data_provider}' is not available. "
            f"Available sources: {list(DATA_SOURCES.keys())}"
        )
elif settings.default_data_provider:
    if settings.default_data_provider in DATA_SOURCES:
        PRIMARY_DATA_SOURCE = settings.default_data_provider
    else:
        raise ValueError(
            f"Default data provider '{settings.default_data_provider}' is not available. "
            f"Available sources: {list(DATA_SOURCES.keys())}"
        )
else:
    PRIMARY_DATA_SOURCE = "fallback"

# Set fallback source
if settings.fallback_data_provider and settings.fallback_data_provider in DATA_SOURCES:
    FALLBACK_DATA_SOURCE = settings.fallback_data_provider
elif PRIMARY_DATA_SOURCE != "fallback":
    # If primary is not "fallback", use "fallback" as fallback (which has Yahoo + Finnhub)
    FALLBACK_DATA_SOURCE = "fallback"
elif "yahoo_finance" in DATA_SOURCES:
    # If primary is "fallback", use yahoo_finance as explicit fallback
    FALLBACK_DATA_SOURCE = "yahoo_finance"
else:
    FALLBACK_DATA_SOURCE = None  # No fallback available

# Final validation: Ensure PRIMARY_DATA_SOURCE is actually available
# Fail fast if required dependencies are missing
if PRIMARY_DATA_SOURCE and not _is_source_available(PRIMARY_DATA_SOURCE):
    import logging
    logger = logging.getLogger(__name__)
    if PRIMARY_DATA_SOURCE == "massive" and not POLYGON_LIBRARY_AVAILABLE:
        error_msg = (
            f"❌ CRITICAL: 'massive' library is not installed but Massive.com is configured.\n"
            f"   'massive>=2.0.0' is in requirements.txt but the Docker container needs to be rebuilt.\n"
            f"   Run: docker-compose build python-worker\n"
            f"   Then: docker-compose up -d python-worker"
        )
        logger.error(error_msg)
        raise ImportError(
            "massive library not installed. Rebuild Docker container: "
            "docker-compose build python-worker && docker-compose up -d python-worker"
        )
    else:
        raise RuntimeError(
            f"PRIMARY_DATA_SOURCE='{PRIMARY_DATA_SOURCE}' is not available. "
            f"Available sources: {list(DATA_SOURCES.keys())}"
        )

# Default data source - use primary (for backward compatibility)
DEFAULT_DATA_SOURCE = PRIMARY_DATA_SOURCE


def get_data_source(name: str = None, use_fallback: bool = True) -> BaseDataSource:
    """
    Factory function to get a data source instance using new adapter architecture
    Industry Standard: Returns primary source, with automatic fallback capability
    
    Args:
        name: Name of data source (defaults to PRIMARY_DATA_SOURCE from config)
               If None, uses configured primary source
        use_fallback: If True and name is None, returns a composite source with fallback
    
    Returns:
        Data source instance (primary source, or composite with fallback if use_fallback=True)
    """
    if name is None:
        name = PRIMARY_DATA_SOURCE
    
    # Try new adapter factory first
    try:
        from app.data_sources.adapters import create_adapter
        from app.config import settings
        from app.data_sources.composite_source import CompositeDataSource
        
        adapter = create_adapter(name)
        if adapter:
            # Prepare configuration based on adapter type
            config = {}
            
            if name == "fmp":
                config = {
                    "api_key": settings.fmp_api_key,
                    "base_url": settings.fmp_base_url,
                    "timeout": settings.fmp_timeout,
                    "max_retries": settings.fmp_max_retries,
                    "retry_delay": settings.fmp_retry_delay,
                    "rate_limit_calls": settings.fmp_rate_limit_calls,
                    "rate_limit_window": settings.fmp_rate_limit_window
                }
            elif name == "massive":
                config = {
                    "api_key": settings.massive_api_key,
                    "rate_limit_calls": settings.massive_rate_limit_calls,
                    "rate_limit_window": settings.massive_rate_limit_window
                }
            elif name == "yahoo_finance":
                config = {
                    "timeout": getattr(settings, 'yahoo_finance_timeout', 30),
                    "retry_count": getattr(settings, 'yahoo_finance_retry_count', 3)
                }
            elif name == "fallback":
                config = {
                    "cache_enabled": getattr(settings, 'fallback_cache_enabled', True),
                    "cache_ttl": getattr(settings, 'fallback_cache_ttl', 3600),
                    "primary_source": getattr(settings, 'fallback_primary_source', 'yahoo_finance')
                }
            
            # Initialize adapter with proper configuration
            adapter.initialize(config)
            if adapter.is_available():
                # If configured, wrap primary adapter with fallback.
                if (
                    use_fallback
                    and name == PRIMARY_DATA_SOURCE
                    and FALLBACK_DATA_SOURCE
                    and FALLBACK_DATA_SOURCE != name
                ):
                    fallback_source = get_data_source(name=FALLBACK_DATA_SOURCE, use_fallback=False)
                    return CompositeDataSource(primary=adapter, fallback=fallback_source)

                return adapter
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Adapter factory failed for {name}: {e}")
    
    # Fall back to legacy sources if adapter fails
    if not _is_source_available(name):
        # Fail fast with clear error message
        if name == "massive" and not POLYGON_LIBRARY_AVAILABLE:
            raise ImportError(
                "massive library not installed. Rebuild Docker container: "
                "docker-compose build python-worker && docker-compose up -d python-worker"
            )
        raise ValueError(
            f"Data source '{name}' is not available. "
            f"Available sources: {list(DATA_SOURCES.keys())}"
        )
    
    # If use_fallback and we have both primary and fallback configured, create composite
    # But only if primary is actually available
    if use_fallback and name == PRIMARY_DATA_SOURCE and FALLBACK_DATA_SOURCE and FALLBACK_DATA_SOURCE != name:
        # Only create composite if both sources are available
        if _is_source_available(PRIMARY_DATA_SOURCE) and _is_source_available(FALLBACK_DATA_SOURCE):
            # Return a composite source that tries primary first, then fallback
            return _create_composite_source(PRIMARY_DATA_SOURCE, FALLBACK_DATA_SOURCE)
        elif _is_source_available(PRIMARY_DATA_SOURCE):
            # Primary available but fallback not - use primary only
            return _get_source_instance(PRIMARY_DATA_SOURCE)
        elif _is_source_available(FALLBACK_DATA_SOURCE):
            # Primary not available but fallback is - use fallback only
            return _get_source_instance(FALLBACK_DATA_SOURCE)
    
    # Return direct source instance
    return _get_source_instance(name)


def _create_composite_source(primary_name: str, fallback_name: str) -> BaseDataSource:
    """
    Create a composite data source with primary and fallback
    Industry Standard: Tries primary first, automatically falls back to fallback on failure
    """
    from app.data_sources.composite_source import CompositeDataSource
    
    # Validate that sources are available before trying to instantiate
    if not _is_source_available(primary_name):
        raise ValueError(
            f"Cannot create composite source: primary source '{primary_name}' is not available. "
            f"Install required dependencies (e.g., 'pip install -U massive' for Massive.com) "
            f"and rebuild Docker container."
        )
    
    if fallback_name and not _is_source_available(fallback_name):
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"Fallback source '{fallback_name}' is not available. "
            f"Creating composite with primary only."
        )
        fallback_name = None
    
    # Get primary source
    primary = _get_source_instance(primary_name)
    
    # Get fallback source
    fallback = _get_source_instance(fallback_name) if fallback_name else None
    
    # Create composite
    return CompositeDataSource(primary=primary, fallback=fallback)


def _get_source_instance(name: str) -> BaseDataSource:
    """Get a single source instance (internal helper)"""
    # Safety check: Don't try to instantiate unavailable sources
    if not _is_source_available(name):
            raise ValueError(
                f"Cannot instantiate data source '{name}': it is not available. "
                f"Available sources: {list(DATA_SOURCES.keys())}. "
                f"For Massive.com, ensure 'massive' library is installed: pip install -U massive"
            )
    
    # Try plugin registry first
    registry = get_registry()
    plugin = registry.get(name)
    
    if plugin and plugin.get_metadata().plugin_type == PluginType.DATA_SOURCE:
        return plugin
    
    # Fall back to legacy registry
    if name in DATA_SOURCES:
        source_class = DATA_SOURCES[name]
        
        # Special handling for Massive.com
        if name == "massive":
            # Double-check massive library availability (should already be checked by _is_source_available)
            if not POLYGON_LIBRARY_AVAILABLE:
                raise ImportError(
                    "massive library not installed. Install with: pip install -U massive. "
                    "Rebuild Docker container after adding to requirements.txt."
                )
            if not settings.massive_api_key:
                raise ValueError("Massive.com API key not configured")
            return source_class(api_key=settings.massive_api_key)
        
        return source_class()
    
    raise ValueError(f"Unknown data source: {name}")


def get_primary_source() -> BaseDataSource:
    """Get the configured primary data source (no fallback)"""
    return get_data_source(name=PRIMARY_DATA_SOURCE, use_fallback=False)


def get_fallback_source() -> Optional[BaseDataSource]:
    """Get the configured fallback data source"""
    if FALLBACK_DATA_SOURCE:
        return get_data_source(name=FALLBACK_DATA_SOURCE, use_fallback=False)
    return None

