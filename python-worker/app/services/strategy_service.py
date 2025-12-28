"""
Strategy Service
Manages strategy selection and execution based on user/portfolio preferences
"""
from typing import Dict, Any, Optional
import pandas as pd

from app.strategies import get_strategy, DEFAULT_STRATEGY, list_strategies
from app.strategies.base import StrategyResult
from app.database import db
from app.services.base import BaseService
from app.utils.exception_handler import handle_database_errors


class StrategyService(BaseService):
    """Service for managing and executing trading strategies"""
    
    def __init__(self):
        """Initialize strategy service"""
        super().__init__()
    
    @handle_database_errors
    def get_user_strategy(self, user_id: str) -> str:
        """
        Get preferred strategy for a user
        
        Returns:
            Strategy name (defaults to 'technical')
        """
        query = """
            SELECT preferred_strategy
            FROM users
            WHERE user_id = :user_id
        """
        
        result = db.execute_query(query, {"user_id": user_id})
        if result and result[0].get('preferred_strategy'):
            return result[0]['preferred_strategy']
        
        return DEFAULT_STRATEGY
    
    def get_portfolio_strategy(self, portfolio_id: str) -> str:
        """
        Get strategy for a portfolio (portfolio-level overrides user-level)
        
        Returns:
            Strategy name
        """
        # First check portfolio-level strategy
        query = """
            SELECT p.strategy_name, u.preferred_strategy, u.user_id
            FROM portfolios p
            JOIN users u ON p.user_id = u.user_id
            WHERE p.portfolio_id = :portfolio_id
        """
        
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        if result:
            row = result[0]
            # Portfolio strategy overrides user strategy
            if row.get('strategy_name'):
                return row['strategy_name']
            # Fall back to user strategy
            if row.get('preferred_strategy'):
                return row['preferred_strategy']
        
        return DEFAULT_STRATEGY
    
    def set_user_strategy(self, user_id: str, strategy_name: str) -> bool:
        """
        Set preferred strategy for a user
        
        Args:
            user_id: User ID
            strategy_name: Strategy name
        
        Returns:
            True if successful
        """
        # Validate strategy exists
        available_strategies = list_strategies()
        if strategy_name not in available_strategies:
            logger.error(f"Strategy '{strategy_name}' not found. Available: {list(available_strategies.keys())}")
            return False
        
        query = """
            UPDATE users
            SET preferred_strategy = :strategy_name, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
        """
        
        try:
            db.execute_update(query, {"user_id": user_id, "strategy_name": strategy_name})
            self.log_info(f"✅ Set strategy '{strategy_name}' for user {user_id}", 
                         context={'strategy_name': strategy_name, 'user_id': user_id})
            return True
        except Exception as e:
            self.log_error("Error setting user strategy", e, context={'user_id': user_id, 'strategy_name': strategy_name})
            return False
    
    def set_portfolio_strategy(self, portfolio_id: str, strategy_name: str) -> bool:
        """
        Set strategy for a portfolio
        
        Args:
            portfolio_id: Portfolio ID
            strategy_name: Strategy name (or NULL to use user default)
        
        Returns:
            True if successful
        """
        # Validate strategy exists (if not NULL)
        if strategy_name:
            available_strategies = list_strategies()
            if strategy_name not in available_strategies:
                self.log_error(f"Strategy '{strategy_name}' not found", None,
                              context={'strategy_name': strategy_name, 'available': list(available_strategies.keys())})
                return False
        
        query = """
            UPDATE portfolios
            SET strategy_name = :strategy_name, updated_at = CURRENT_TIMESTAMP
            WHERE portfolio_id = :portfolio_id
        """
        
        try:
            db.execute_update(query, {"portfolio_id": portfolio_id, "strategy_name": strategy_name})
            self.log_info(f"✅ Set strategy '{strategy_name}' for portfolio {portfolio_id}", 
                         context={'strategy_name': strategy_name, 'portfolio_id': portfolio_id})
            return True
        except Exception as e:
            self.log_error("Error setting portfolio strategy", e, 
                          context={'portfolio_id': portfolio_id, 'strategy_name': strategy_name})
            return False
    
    def execute_strategy(
        self,
        strategy_name: str,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> StrategyResult:
        """
        Execute a strategy and return signal
        
        Args:
            strategy_name: Name of the strategy to execute
            indicators: Dictionary of calculated indicators
            market_data: Optional historical market data
            context: Optional context (symbol, user_id, etc.)
            config: Optional strategy-specific configuration
        
        Returns:
            StrategyResult with signal, confidence, reason
        """
        strategy = get_strategy(strategy_name, config=config)
        
        if not strategy:
            self.log_error(f"Strategy '{strategy_name}' not found, using default", None,
                          context={'strategy_name': strategy_name, 'default': DEFAULT_STRATEGY})
            strategy = get_strategy(DEFAULT_STRATEGY, config=config)
        
        if not strategy:
            # Fallback if even default strategy fails
            return StrategyResult(
                signal='hold',
                confidence=0.0,
                reason="No strategy available",
                metadata={},
                strategy_name="unknown"
            )
        
        # Pre-validation: Check data sufficiency before execution
        is_valid, validation_error = strategy.validate_indicators(indicators, market_data)
        if not is_valid:
            self.log_warning(f"Strategy '{strategy_name}' validation failed: {validation_error}", 
                           context={'strategy_name': strategy_name, 'validation_error': validation_error})
            return StrategyResult(
                signal='hold',
                confidence=0.0,
                reason=f"Data validation failed: {validation_error}",
                metadata={'validation_error': validation_error},
                strategy_name=strategy_name
            )
        
        try:
            result = strategy.generate_signal(indicators, market_data, context)
            self.logger.debug(f"Strategy '{strategy_name}' generated signal: {result.signal} (confidence: {result.confidence:.2f})")
            return result
        except Exception as e:
            self.log_error(f"Error executing strategy '{strategy_name}'", e, 
                          context={'strategy_name': strategy_name, 'symbol': context.get('symbol')})
            return StrategyResult(
                signal='hold',
                confidence=0.0,
                reason=f"Strategy execution error: {str(e)}",
                metadata={},
                strategy_name=strategy_name
            )
    
    def list_available_strategies(self) -> Dict[str, str]:
        """
        List all available strategies
        
        Returns:
            Dictionary mapping strategy names to descriptions
        """
        return list_strategies()

