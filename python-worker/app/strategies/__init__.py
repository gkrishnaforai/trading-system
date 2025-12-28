"""
Pluggable Trading Strategy System
Allows multiple strategies to be registered and selected per user/portfolio
"""

from app.strategies.base import BaseStrategy, StrategyResult
from app.strategies.registry import StrategyRegistry, get_strategy, register_strategy, list_strategies
from app.strategies.technical_strategy import TechnicalStrategy
from app.strategies.hybrid_llm_strategy import HybridLLMStrategy
from app.strategies.screener_strategy import ScreenerStrategy

__all__ = [
    "BaseStrategy",
    "StrategyResult",
    "StrategyRegistry",
    "get_strategy",
    "register_strategy",
    "list_strategies",
    "TechnicalStrategy",
    "HybridLLMStrategy",
    "ScreenerStrategy",
]

# Default strategy name
DEFAULT_STRATEGY = "technical"


# Auto-register strategies on import
def _register_default_strategies():
    """Register default strategies"""
    register_strategy(TechnicalStrategy)
    register_strategy(HybridLLMStrategy)
    register_strategy(ScreenerStrategy)
    
    # Register swing strategies (Elite & Admin only)
    from app.strategies.swing.trend_strategy import SwingTrendStrategy
    register_strategy(SwingTrendStrategy)


# Register strategies when module is imported
_register_default_strategies()
