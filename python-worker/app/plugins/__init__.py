"""
Plugin System for Trading System
DRY & SOLID: Centralized plugin management with best practices
Industry Standard: Plugin Registry Pattern with dynamic loading
Supports: Data Sources, Strategies, Indicators, AI Agents, Workflows
"""

# Core plugin interfaces
from .base import (
    Plugin,
    PluginType,
    PluginMetadata,
    DataSourcePlugin,
    StrategyPlugin,
    IndicatorPlugin,
    AgentPlugin,
    WorkflowPlugin
)

# Adapter framework with error handling
from .base_adapter import (
    BasePluginAdapter,
    DataSourceAdapter,
    PluginError,
    PluginInitializationError,
    PluginAvailabilityError,
    handle_plugin_errors
)

# Data source adapters with best practices (lazy import to avoid circular dependency)
def get_massive_adapter():
    from .data_source_adapters import MassivePluginAdapter
    return MassivePluginAdapter

def get_yahoo_finance_adapter():
    from .data_source_adapters import YahooFinancePluginAdapter
    return YahooFinancePluginAdapter

def get_fallback_adapter():
    from .data_source_adapters import FallbackPluginAdapter
    return FallbackPluginAdapter

def create_data_source_adapters():
    from .data_source_adapters import create_data_source_adapters as _create_adapters
    return _create_adapters()

# Registration management (lazy import to avoid circular dependency)
def get_registration_manager():
    from .registration_manager import get_registration_manager as _get_manager
    return _get_manager()

def initialize_data_sources(config=None):
    from .registration_manager import initialize_data_sources as _init_sources
    return _init_sources(config)

# Registry
from .registry import PluginRegistry, get_registry as get_plugin_registry

# Backward compatibility - provide get_registry alias
def get_registry():
    """Get the global plugin registry (backward compatibility)"""
    return get_plugin_registry()

# Version information for compatibility tracking
__version__ = "1.0.0"
__author__ = "Trading System"

__all__ = [
    # Core classes
    'Plugin',
    'PluginType',
    'PluginMetadata',
    'DataSourcePlugin',
    'StrategyPlugin',
    'IndicatorPlugin',
    'AgentPlugin',
    'WorkflowPlugin',
    
    # Adapter framework
    'BasePluginAdapter',
    'DataSourceAdapter',
    'PluginError',
    'PluginInitializationError',
    'PluginAvailabilityError',
    'handle_plugin_errors',
    
    # Data source adapters (lazy loading)
    'get_massive_adapter',
    'get_yahoo_finance_adapter',
    'get_fallback_adapter',
    'create_data_source_adapters',
    
    # Registration management (lazy loading)
    'get_registration_manager',
    'initialize_data_sources',
    
    # Registry
    'PluginRegistry',
    'get_plugin_registry',
    'get_registry',  # Backward compatibility
]

