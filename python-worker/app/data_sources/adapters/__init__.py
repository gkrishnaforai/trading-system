"""
Data Source Adapters Package
SOLID: Single responsibility for adapter management
DRY: Centralized adapter exports and factory
Performance: Lazy loading, singleton pattern
"""

# Core adapter framework
from .base_adapter import (
    BaseDataSourceAdapter,
    AdapterError,
    AdapterInitializationError,
    AdapterUnavailableError,
    PerformanceMetrics
)

# Specific adapter implementations
from .yahoo_finance_adapter import YahooFinanceAdapter
from .massive_adapter import MassiveAdapter
from .fallback_adapter import FallbackAdapter

# Factory and management
from .factory import (
    AdapterFactory,
    AdapterConfig,
    get_adapter_factory,
    create_adapter,
    create_all_adapters
)

# Version information
__version__ = "2.0.0"
__author__ = "Trading System"

# Public API
__all__ = [
    # Core framework
    "BaseDataSourceAdapter",
    "AdapterError",
    "AdapterInitializationError", 
    "AdapterUnavailableError",
    "PerformanceMetrics",
    
    # Adapter implementations
    "YahooFinanceAdapter",
    "MassiveAdapter",
    "FallbackAdapter",
    
    # Factory and management
    "AdapterFactory",
    "AdapterConfig",
    "get_adapter_factory",
    "create_adapter",
    "create_all_adapters"
]
