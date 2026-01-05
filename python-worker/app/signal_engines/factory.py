"""
Signal Engine Factory
Manages registration and instantiation of signal engines
"""

from typing import Dict, Type, List, Optional
from app.observability.logging import get_logger

from .base import BaseSignalEngine, SignalEngineError

logger = get_logger(__name__)


class SignalEngineFactory:
    """Factory pattern implementation for signal engines"""
    
    _engines: Dict[str, Type[BaseSignalEngine]] = {}
    _instances: Dict[str, BaseSignalEngine] = {}
    
    @classmethod
    def register_engine(cls, name: str, engine_class: Type[BaseSignalEngine]) -> None:
        """
        Register a signal engine class
        
        Args:
            name: Engine identifier (e.g., 'legacy', 'adaptive_fundamental')
            engine_class: Engine class that inherits from BaseSignalEngine
        """
        if not issubclass(engine_class, BaseSignalEngine):
            raise SignalEngineError(f"Engine class {engine_class} must inherit from BaseSignalEngine")
        
        cls._engines[name.lower()] = engine_class
        logger.info(f"Registered signal engine: {name}")
    
    @classmethod
    def get_engine(cls, name: str) -> BaseSignalEngine:
        """
        Get an instance of the specified engine
        
        Args:
            name: Engine identifier
            
        Returns:
            Engine instance
            
        Raises:
            SignalEngineError: If engine is not registered
        """
        name = name.lower()
        
        if name not in cls._engines:
            available = ', '.join(cls._engines.keys())
            raise SignalEngineError(f"Engine '{name}' not registered. Available: {available}")
        
        # Use singleton pattern for instances
        if name not in cls._instances:
            try:
                cls._instances[name] = cls._engines[name]()
                logger.info(f"Created engine instance: {name}")
            except Exception as e:
                raise SignalEngineError(f"Failed to create engine instance '{name}': {str(e)}")
        
        return cls._instances[name]
    
    @classmethod
    def get_available_engines(cls) -> List[Dict[str, str]]:
        """
        Get list of all registered engines with metadata
        
        Returns:
            List of engine info dictionaries
        """
        engines = []
        for name, engine_class in cls._engines.items():
            try:
                # Create temporary instance to get metadata
                temp_instance = engine_class()
                metadata = temp_instance.get_engine_metadata()
                
                engines.append({
                    'name': name,
                    'display_name': metadata.get('display_name', name.title()),
                    'description': metadata.get('description', ''),
                    'tier': metadata.get('tier', 'BASIC'),
                    'timeframe': metadata.get('timeframe', 'position'),
                    'version': metadata.get('version', '1.0.0')
                })
            except Exception as e:
                logger.warning(f"Failed to get metadata for engine {name}: {str(e)}")
                engines.append({
                    'name': name,
                    'display_name': name.title(),
                    'description': 'Error loading metadata',
                    'tier': 'UNKNOWN',
                    'timeframe': 'unknown',
                    'version': 'unknown'
                })
        
        return engines
    
    @classmethod
    def get_engines_by_tier(cls, tier: str) -> List[Dict[str, str]]:
        """
        Get engines filtered by access tier
        
        Args:
            tier: Tier level (BASIC, PRO, ELITE)
            
        Returns:
            List of engines in specified tier
        """
        all_engines = cls.get_available_engines()
        return [engine for engine in all_engines if engine['tier'].upper() == tier.upper()]
    
    @classmethod
    def clear_instances(cls) -> None:
        """Clear all engine instances (useful for testing)"""
        cls._instances.clear()
        logger.info("Cleared all engine instances")


# Auto-register engines when imported
def _register_builtin_engines():
    """Register all built-in signal engines"""
    from .legacy_engine import LegacyEngine
    from .adaptive_fundamental_engine import AdaptiveFundamentalEngine
    from .swing_regime_engine import SwingRegimeEngine
    from .position_regime_engine import PositionRegimeEngine
    from .universal_valuation_engine import UniversalValuationEngine
    from .generic_swing_engine import GenericSwingEngine
    from .tqqq_swing_engine import TQQQSwingEngine
    
    SignalEngineFactory.register_engine('legacy', LegacyEngine)
    SignalEngineFactory.register_engine('adaptive_fundamental', AdaptiveFundamentalEngine)
    SignalEngineFactory.register_engine('swing_regime', SwingRegimeEngine)
    SignalEngineFactory.register_engine('position_regime', PositionRegimeEngine)
    SignalEngineFactory.register_engine('universal_valuation', UniversalValuationEngine)
    SignalEngineFactory.register_engine('generic_swing', GenericSwingEngine)
    SignalEngineFactory.register_engine('tqqq_swing', TQQQSwingEngine)

# Register engines on module import
_register_builtin_engines()
