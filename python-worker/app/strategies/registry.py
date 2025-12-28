"""
Strategy Registry
Manages available strategies and allows dynamic registration
"""
import logging
from typing import Dict, Optional, Type
from app.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry for managing trading strategies"""
    
    _instance = None
    _strategies: Dict[str, Type[BaseStrategy]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, strategy_class: Type[BaseStrategy]) -> None:
        """
        Register a strategy class
        
        Args:
            strategy_class: Strategy class that extends BaseStrategy
        """
        strategy_instance = strategy_class()
        strategy_name = strategy_instance.get_name()
        
        if strategy_name in self._strategies:
            logger.warning(f"Strategy '{strategy_name}' already registered. Overwriting.")
        
        self._strategies[strategy_name] = strategy_class
        logger.info(f"✅ Registered strategy: {strategy_name}")
    
    def get(self, strategy_name: str, config: Optional[Dict] = None) -> Optional[BaseStrategy]:
        """
        Get a strategy instance by name
        
        Args:
            strategy_name: Name of the strategy
            config: Optional configuration for the strategy
        
        Returns:
            Strategy instance or None if not found
        """
        if strategy_name not in self._strategies:
            logger.error(f"Strategy '{strategy_name}' not found. Available: {list(self._strategies.keys())}")
            return None
        
        strategy_class = self._strategies[strategy_name]
        return strategy_class(config=config)
    
    def list_strategies(self) -> Dict[str, str]:
        """
        List all registered strategies with descriptions
        
        Returns:
            Dictionary mapping strategy names to descriptions
        """
        result = {}
        for name, strategy_class in self._strategies.items():
            instance = strategy_class()
            result[name] = instance.get_description()
        return result
    
    def is_registered(self, strategy_name: str) -> bool:
        """Check if a strategy is registered"""
        return strategy_name in self._strategies


# Global registry instance
_registry = StrategyRegistry()


def register_strategy(strategy_class: Type[BaseStrategy]) -> None:
    """Register a strategy (convenience function)"""
    _registry.register(strategy_class)


def get_strategy(strategy_name: str, config: Optional[Dict] = None) -> Optional[BaseStrategy]:
    """Get a strategy instance (convenience function)"""
    return _registry.get(strategy_name, config)


def list_strategies() -> Dict[str, str]:
    """List all registered strategies (convenience function)"""
    return _registry.list_strategies()

