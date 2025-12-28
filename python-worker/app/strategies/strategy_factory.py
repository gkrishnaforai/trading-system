"""
Strategy Factory
Creates and manages strategy instances using the registry
"""

from typing import Dict, Optional, List, Any
from app.strategies.registry import get_strategy, list_strategies
from app.strategies.base import BaseStrategy
from app.observability.logging import get_logger

logger = get_logger(__name__)


class StrategyFactory:
    """Factory for creating and managing trading strategies"""
    
    def __init__(self):
        """Initialize strategy factory"""
        self._ensure_strategies_loaded()
    
    def _ensure_strategies_loaded(self):
        """Ensure all strategies are registered"""
        try:
            # Import all strategy modules to trigger registration
            from app.strategies import technical_strategy
            from app.strategies import hybrid_llm_strategy
            from app.strategies import screener_strategy
            
            # Import swing strategies
            from app.strategies.swing import trend_strategy
            
            logger.info("Strategy factory initialized with available strategies")
            
        except ImportError as e:
            logger.warning(f"Could not import some strategy modules: {e}")
    
    def create_strategy(self, strategy_name: str, config: Optional[Dict] = None) -> Optional[BaseStrategy]:
        """
        Create a strategy instance
        
        Args:
            strategy_name: Name of the strategy
            config: Optional configuration for the strategy
            
        Returns:
            Strategy instance or None if not found
        """
        try:
            strategy = get_strategy(strategy_name, config)
            if strategy:
                logger.debug(f"Created strategy: {strategy_name}")
            else:
                logger.warning(f"Strategy not found: {strategy_name}")
            return strategy
            
        except Exception as e:
            logger.error(f"Error creating strategy {strategy_name}: {e}")
            return None
    
    def get_available_strategies(self) -> Dict[str, str]:
        """
        Get list of available strategies with descriptions
        
        Returns:
            Dictionary mapping strategy names to descriptions
        """
        try:
            return list_strategies()
        except Exception as e:
            logger.error(f"Error getting available strategies: {e}")
            return {}
    
    def execute_strategy(
        self, 
        strategy_name: str, 
        indicators: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a strategy and return results
        
        Args:
            strategy_name: Name of the strategy
            indicators: Technical indicators data
            context: Optional context (symbol, timestamp, etc.)
            
        Returns:
            Strategy execution results
        """
        try:
            strategy = self.create_strategy(strategy_name)
            if not strategy:
                return {
                    "error": f"Strategy '{strategy_name}' not available",
                    "signal": "HOLD",
                    "confidence": 0.0,
                    "reason": "Strategy not found"
                }
            
            # Validate indicators
            if not indicators:
                return {
                    "error": "No indicators provided",
                    "signal": "HOLD", 
                    "confidence": 0.0,
                    "reason": "Missing indicator data"
                }
            
            # Execute strategy using the correct method name
            result = strategy.generate_signal(indicators, context=context)
            
            # Convert StrategyResult to dictionary
            if hasattr(result, 'signal'):
                return {
                    "signal": result.signal,
                    "confidence": result.confidence,
                    "reason": result.reason,
                    "metadata": result.metadata,
                    "strategy_name": strategy_name
                }
            else:
                # If result is already a dictionary
                result["strategy_name"] = strategy_name
                return result
            
        except Exception as e:
            logger.error(f"Error executing strategy {strategy_name}: {e}")
            return {
                "error": str(e),
                "signal": "HOLD",
                "confidence": 0.0,
                "reason": f"Strategy execution failed: {str(e)}",
                "strategy_name": strategy_name
            }
    
    def validate_strategy_requirements(self, strategy_name: str, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate if indicators meet strategy requirements
        
        Args:
            strategy_name: Name of the strategy
            indicators: Available indicators
            
        Returns:
            Validation result with missing requirements
        """
        try:
            strategy = self.create_strategy(strategy_name)
            if not strategy:
                return {
                    "valid": False,
                    "error": f"Strategy '{strategy_name}' not found",
                    "missing_requirements": []
                }
            
            # Get strategy requirements (if method exists)
            if hasattr(strategy, 'get_required_indicators'):
                required = strategy.get_required_indicators()
                missing = [ind for ind in required if ind not in indicators]
                
                return {
                    "valid": len(missing) == 0,
                    "missing_requirements": missing,
                    "available_indicators": list(indicators.keys())
                }
            else:
                # Default validation - check for common indicators
                common_indicators = ['price', 'ema20', 'ema50', 'sma200', 'rsi', 'macd_line', 'macd_signal']
                missing = [ind for ind in common_indicators if ind not in indicators]
                
                return {
                    "valid": len(missing) <= len(common_indicators) // 2,  # Allow some missing
                    "missing_requirements": missing,
                    "available_indicators": list(indicators.keys())
                }
                
        except Exception as e:
            logger.error(f"Error validating strategy {strategy_name}: {e}")
            return {
                "valid": False,
                "error": str(e),
                "missing_requirements": []
            }
