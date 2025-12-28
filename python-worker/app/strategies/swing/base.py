"""
Base Swing Trading Strategy
All swing strategies extend this class
Industry Standard: Swing trading strategy interface
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd

from app.strategies.base import BaseStrategy, StrategyResult
from app.exceptions import ValidationError


@dataclass
class SwingStrategyResult:
    """
    Result from swing trading strategy
    
    Industry Standard: Comprehensive signal with entry/exit levels
    """
    signal: str  # 'BUY', 'SELL', 'HOLD'
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float  # Percentage of portfolio (0.01 = 1%)
    confidence: float  # 0.0 to 1.0
    timeframe: str  # 'daily', 'weekly'
    entry_reason: str
    exit_reason: Optional[str] = None
    risk_reward_ratio: float = 0.0
    max_hold_days: int = 7
    
    def __post_init__(self):
        """Validate result data"""
        if self.signal not in ['BUY', 'SELL', 'HOLD']:
            raise ValidationError(f"Invalid signal: {self.signal}")
        
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValidationError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")
        
        if self.timeframe not in ['daily', 'weekly']:
            raise ValidationError(f"Invalid timeframe: {self.timeframe}")


class BaseSwingStrategy(BaseStrategy):
    """
    Base class for all swing trading strategies
    
    SOLID: Open/Closed Principle - open for extension, closed for modification
    DRY: Common swing trading logic in base class
    
    Features:
    - Multi-timeframe analysis
    - Risk-adjusted signals
    - Position sizing recommendations
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize swing strategy
        
        Args:
            config: Strategy configuration
                - max_hold_days: Maximum days to hold (default: 7)
                - risk_per_trade: Risk per trade as decimal (default: 0.01 = 1%)
        """
        super().__init__(config)
        self.max_hold_days = config.get('max_hold_days', 7) if config else 7
        self.risk_per_trade = config.get('risk_per_trade', 0.01) if config else 0.01  # 1%
        
        if self.max_hold_days < 1 or self.max_hold_days > 30:
            raise ValidationError(f"max_hold_days must be between 1 and 30, got {self.max_hold_days}")
        
        if self.risk_per_trade <= 0 or self.risk_per_trade > 0.1:
            raise ValidationError(f"risk_per_trade must be between 0 and 0.1, got {self.risk_per_trade}")
    
    def get_required_indicators(self) -> list:
        """
        Return list of required indicator names for swing strategies
        
        Swing strategies primarily use market_data, but can use pre-calculated indicators
        
        Returns:
            List of required indicator names (empty for swing - uses market_data directly)
        """
        return []  # Swing strategies use market_data directly, not pre-calculated indicators
    
    def _get_minimum_market_data_points(self) -> int:
        """
        Get minimum market data points required for swing strategies
        
        Returns:
            Minimum number of data points required (50 for swing strategies)
        """
        return 50  # Swing strategies need at least 50 periods for reliable signals
    
    @abstractmethod
    def generate_swing_signal(
        self,
        daily_data: pd.DataFrame,
        weekly_data: Optional[pd.DataFrame] = None,
        indicators: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> SwingStrategyResult:
        """
        Generate swing trading signal
        
        Args:
            daily_data: Daily price data (required)
            weekly_data: Weekly price data (optional, for trend confirmation)
            indicators: Pre-calculated indicators (optional)
            context: Additional context (user preferences, account balance, etc.)
        
        Returns:
            SwingStrategyResult with entry/exit signals
        
        Raises:
            ValidationError: If inputs are invalid
        """
        pass
    
    def generate_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Implement BaseStrategy.generate_signal() for swing strategies
        
        This method adapts the base strategy interface to swing trading.
        It converts the swing signal result to a standard StrategyResult.
        
        Args:
            indicators: Dictionary of indicators (not used directly for swing)
            market_data: Market data DataFrame (used as daily_data)
            context: Additional context
        
        Returns:
            StrategyResult compatible with base strategy interface
        """
        if market_data is None or market_data.empty:
            return StrategyResult(
                signal='hold',
                confidence=0.0,
                reason="No market data provided",
                metadata={},
                strategy_name=self.get_name()
            )
        
        # Normalize market_data to daily_data format
        daily_data = market_data.copy()
        
        # Get weekly data from context if available
        weekly_data = context.get('weekly_data') if context else None
        
        try:
            # Generate swing signal
            swing_result = self.generate_swing_signal(
                daily_data=daily_data,
                weekly_data=weekly_data,
                indicators=indicators,
                context=context
            )
            
            # Convert SwingStrategyResult to StrategyResult
            signal_map = {
                'BUY': 'buy',
                'SELL': 'sell',
                'HOLD': 'hold'
            }
            
            return StrategyResult(
                signal=signal_map.get(swing_result.signal, 'hold'),
                confidence=swing_result.confidence,
                reason=swing_result.entry_reason or swing_result.exit_reason or "No signal",
                metadata={
                    'entry_price': swing_result.entry_price,
                    'stop_loss': swing_result.stop_loss,
                    'take_profit': swing_result.take_profit,
                    'position_size': swing_result.position_size,
                    'risk_reward_ratio': swing_result.risk_reward_ratio,
                    'max_hold_days': swing_result.max_hold_days,
                    'timeframe': swing_result.timeframe
                },
                strategy_name=self.get_name()
            )
            
        except Exception as e:
            # Fail fast - return low confidence hold on error
            return StrategyResult(
                signal='hold',
                confidence=0.0,
                reason=f"Error generating swing signal: {str(e)}",
                metadata={'error': str(e)},
                strategy_name=self.get_name()
            )
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        risk_per_trade: Optional[float] = None
    ) -> float:
        """
        Calculate position size based on risk
        
        Industry Standard: Fixed fractional position sizing
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            account_balance: Total account balance
            risk_per_trade: Risk per trade (default: self.risk_per_trade)
        
        Returns:
            Position size as percentage of portfolio (0.01 = 1%)
        
        Raises:
            ValidationError: If inputs are invalid
        """
        if entry_price <= 0:
            raise ValidationError(f"Entry price must be positive, got {entry_price}")
        
        if account_balance <= 0:
            raise ValidationError(f"Account balance must be positive, got {account_balance}")
        
        risk_pct = risk_per_trade or self.risk_per_trade
        risk_amount = account_balance * risk_pct
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk == 0:
            return 0.0
        
        position_value = risk_amount / (price_risk / entry_price)
        position_size_pct = position_value / account_balance
        
        # Cap at 10% per position
        return min(position_size_pct, 0.10)
    
    def calculate_risk_reward(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> float:
        """
        Calculate risk-reward ratio
        
        Industry Standard: Reward / Risk ratio
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            Risk-reward ratio (e.g., 3.0 = 3:1)
        """
        if entry_price <= 0:
            raise ValidationError(f"Entry price must be positive, got {entry_price}")
        
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        
        if risk == 0:
            return 0.0
        
        return reward / risk

