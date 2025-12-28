"""
Base Strategy Interface
All strategies must implement this interface
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@dataclass
class StrategyResult:
    """Result from a strategy execution"""
    signal: str  # 'buy', 'sell', 'hold'
    confidence: float  # 0.0 to 1.0
    reason: str  # Human-readable explanation
    metadata: Dict[str, Any]  # Additional strategy-specific data
    strategy_name: str  # Name of the strategy that generated this result


class BaseStrategy(ABC):
    """
    Base class for all trading strategies
    
    Each strategy must implement:
    - generate_signal(): Generate buy/sell/hold signal
    - get_name(): Return strategy identifier
    - get_description(): Return human-readable description
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with optional configuration
        
        Args:
            config: Strategy-specific configuration dictionary
        """
        self.config = config or {}
        self.name = self.get_name()
    
    @abstractmethod
    def get_name(self) -> str:
        """
        Return unique strategy identifier
        
        Returns:
            Strategy name (e.g., 'technical', 'hybrid_llm')
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """
        Return human-readable strategy description
        
        Returns:
            Strategy description
        """
        pass
    
    @abstractmethod
    def generate_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> StrategyResult:
        """
        Generate trading signal based on indicators and context
        
        Args:
            indicators: Dictionary of calculated indicators
                - price, ema20, ema50, sma200
                - macd_line, macd_signal, macd_histogram
                - rsi, atr, volume, volume_ma
                - long_term_trend, medium_term_trend
            market_data: Optional DataFrame with historical price data
            context: Optional context (e.g., user preferences, portfolio info)
        
        Returns:
            StrategyResult with signal, confidence, reason, and metadata
        """
        pass
    
    def validate_config(self) -> bool:
        """
        Validate strategy configuration
        
        Returns:
            True if configuration is valid
        """
        return True
    
    def get_required_indicators(self) -> list:
        """
        Return list of required indicator names
        
        Returns:
            List of required indicator names
        """
        return []
    
    def validate_indicators(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None
    ) -> Tuple[bool, str]:
        """
        Validate that required indicators exist and have sufficient data
        
        Args:
            indicators: Dictionary of indicators
            market_data: Optional market data DataFrame
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        required = self.get_required_indicators()
        if not required:
            return True, ""
        
        missing = []
        insufficient = []
        invalid = []
        
        for indicator_name in required:
            indicator = indicators.get(indicator_name)
            
            # Check if indicator exists
            if indicator is None:
                missing.append(indicator_name)
                continue
            
            # Check if it's a Series with enough data
            if isinstance(indicator, pd.Series):
                # Check minimum data points based on indicator type
                min_points = self._get_minimum_data_points(indicator_name)
                if len(indicator) < min_points:
                    insufficient.append(f"{indicator_name} (need {min_points}, have {len(indicator)})")
                    continue
                
                # Check if latest value is valid (not NaN)
                if len(indicator) > 0 and pd.isna(indicator.iloc[-1]):
                    invalid.append(f"{indicator_name} (latest value is NaN)")
            elif isinstance(indicator, (int, float, type(None))):
                # Scalar value - check if it's valid
                if indicator is None:
                    missing.append(indicator_name)  # Treat None as missing
                elif pd.isna(indicator):
                    invalid.append(f"{indicator_name} (value is NaN)")
                # Note: Scalar values are acceptable for some use cases (e.g., latest values from DB)
                # But we should warn if critical indicators are scalars when Series are expected
                if indicator_name in ['sma200', 'sma50', 'ema50', 'ema20']:
                    # These typically need Series for proper validation, but scalars might work
                    # The strategy will handle this, but we log a warning
                    pass
            elif isinstance(indicator, str):
                # String values (e.g., trend indicators like 'bullish', 'bearish')
                # These are valid
                pass
            else:
                # Unknown type - might be valid, but log for debugging
                logger.warning(f"Indicator {indicator_name} has unexpected type: {type(indicator).__name__}")
        
        # Check market data if required
        if market_data is not None and not market_data.empty:
            min_market_data_points = self._get_minimum_market_data_points()
            if len(market_data) < min_market_data_points:
                insufficient.append(f"market_data (need {min_market_data_points}, have {len(market_data)})")
        
        # Build error message
        errors = []
        if missing:
            errors.append(f"Missing indicators: {', '.join(missing)}")
        if insufficient:
            errors.append(f"Insufficient data: {', '.join(insufficient)}")
        if invalid:
            errors.append(f"Invalid values: {', '.join(invalid)}")
        
        if errors:
            return False, ". ".join(errors)
        
        return True, ""
    
    def _get_minimum_data_points(self, indicator_name: str) -> int:
        """
        Get minimum data points required for an indicator
        
        Args:
            indicator_name: Name of the indicator
        
        Returns:
            Minimum number of data points required
        """
        # Default minimums based on indicator type
        min_points_map = {
            'sma200': 200,
            'sma50': 50,
            'ema50': 50,
            'ema20': 20,
            'ema9': 9,
            'ema21': 21,
            'rsi': 14,  # RSI typically needs 14 periods
            'macd_line': 26,  # MACD needs EMA12 (12) + EMA26 (26) + signal (9)
            'macd_signal': 26,
            'atr': 14,  # ATR typically uses 14 periods
            'price': 1,
            'volume': 1,
        }
        
        return min_points_map.get(indicator_name, 1)
    
    def _get_minimum_market_data_points(self) -> int:
        """
        Get minimum market data points required
        
        Returns:
            Minimum number of data points required
        """
        # Default to 200 (for SMA200 calculation)
        return 200

