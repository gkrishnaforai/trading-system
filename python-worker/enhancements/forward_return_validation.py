"""
Forward Return Validation Enhancement
Add outcome tracking to optimize for signal quality, not just frequency
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import pandas as pd
import sys
import os
sys.path.append('/app')
from app.signal_engines.signal_calculator_core import MarketConditions, SignalConfig, SignalResult, SignalType

@dataclass
class ForwardReturnMetrics:
    """Metrics for validating signal quality after signal generation"""
    signal_date: str
    signal_price: float
    signal_type: str  # BUY/SELL/HOLD
    
    # Forward returns (3-day, 5-day, 7-day)
    return_3d: float
    return_5d: float
    return_7d: float
    
    # Risk metrics
    max_adverse_excursion: float  # Worst drawdown after signal
    max_favorable_excursion: float  # Best gain after signal
    
    # Outcome classification
    is_profitable_3d: bool
    is_profitable_5d: bool
    bounce_successful: bool  # Did price stop making lower lows?
    
    # Market context at signal time
    rsi_at_signal: float
    volatility_at_signal: float
    trend_at_signal: str  # uptrend/downtrend/sideways

class SignalQualityValidator:
    """Validates signal quality by measuring forward returns"""
    
    def __init__(self, price_data: pd.DataFrame):
        self.price_data = price_data.set_index('date')
        self.signal_history: List[ForwardReturnMetrics] = []
    
    def calculate_forward_returns(self, signal_date: str, signal_price: float, 
                                signal_type: str, rsi: float, volatility: float) -> Optional[ForwardReturnMetrics]:
        """Calculate forward returns for a given signal"""
        
        # Convert to datetime if needed
        if isinstance(signal_date, str):
            signal_date = pd.to_datetime(signal_date).date()
        
        # Get forward price data
        try:
            current_idx = self.price_data.index.get_loc(signal_date)
            
            # Check if we have enough forward data
            days_needed = 7  # Need 7 days for 7-day return analysis
            if current_idx + days_needed >= len(self.price_data):
                # Not enough forward data - return None to avoid survivorship bias
                return None
            
            # 3-day, 5-day, 7-day forward returns
            returns_3d = self._calculate_return(current_idx, signal_price, 3)
            returns_5d = self._calculate_return(current_idx, signal_price, 5)
            returns_7d = self._calculate_return(current_idx, signal_price, 7)
            
            # Risk metrics
            mae, mfe = self._calculate_excursions(current_idx, signal_price, 7)
            
            # Bounce detection (for BUY signals)
            bounce_successful = self._detect_bounce(current_idx, signal_price, 5) if signal_type == "BUY" else True
            
            # Profitability
            is_profitable_3d = returns_3d > 0
            is_profitable_5d = returns_5d > 0
            
            # Trend classification
            trend_at_signal = self._classify_trend(current_idx)
            
            metrics = ForwardReturnMetrics(
                signal_date=str(signal_date),
                signal_price=signal_price,
                signal_type=signal_type,
                return_3d=returns_3d,
                return_5d=returns_5d,
                return_7d=returns_7d,
                max_adverse_excursion=mae,
                max_favorable_excursion=mfe,
                is_profitable_3d=is_profitable_3d,
                is_profitable_5d=is_profitable_5d,
                bounce_successful=bounce_successful,
                rsi_at_signal=rsi,
                volatility_at_signal=volatility,
                trend_at_signal=trend_at_signal
            )
            
            self.signal_history.append(metrics)
            return metrics
            
        except (KeyError, IndexError):
            # Not enough forward data or other error
            return None
    
    def _calculate_return(self, start_idx: int, entry_price: float, days_forward: int) -> float:
        """Calculate return for N days forward"""
        if start_idx + days_forward >= len(self.price_data):
            return 0.0  # Not enough data
        
        exit_price = self.price_data.iloc[start_idx + days_forward]['close']
        return (exit_price - entry_price) / entry_price
    
    def _calculate_excursions(self, start_idx: int, entry_price: float, days_forward: int) -> tuple:
        """Calculate maximum adverse and favorable excursions"""
        if start_idx + days_forward >= len(self.price_data):
            return 0.0, 0.0
        
        forward_data = self.price_data.iloc[start_idx:start_idx + days_forward + 1]
        
        # Maximum adverse excursion (worst drawdown)
        min_price = forward_data['close'].min()
        mae = (entry_price - min_price) / entry_price if min_price < entry_price else 0.0
        
        # Maximum favorable excursion (best gain)
        max_price = forward_data['close'].max()
        mfe = (max_price - entry_price) / entry_price if max_price > entry_price else 0.0
        
        return mae, mfe
    
    def _detect_bounce(self, start_idx: int, entry_price: float, days_forward: int) -> bool:
        """Detect if price successfully bounced after BUY signal"""
        if start_idx + days_forward >= len(self.price_data):
            return False
        
        forward_data = self.price_data.iloc[start_idx:start_idx + days_forward + 1]
        
        # Check if price stopped making lower lows
        lows = forward_data['low'].values
        entry_low = forward_data.iloc[0]['low']
        
        # Successful bounce: no lower lows than entry day
        return all(low >= entry_low for low in lows[1:])
    
    def _classify_trend(self, start_idx: int) -> str:
        """Classify trend at signal time"""
        if start_idx < 20:
            return "insufficient_data"
        
        # Use 20-day SMA for trend classification
        recent_data = self.price_data.iloc[start_idx-20:start_idx]
        sma_20 = recent_data['close'].mean()
        
        current_price = self.price_data.iloc[start_idx]['close']
        
        if current_price > sma_20 * 1.02:
            return "uptrend"
        elif current_price < sma_20 * 0.98:
            return "downtrend"
        else:
            return "sideways"
    
    def get_quality_metrics(self) -> Dict:
        """Get overall signal quality metrics (excluding None values to avoid survivorship bias)"""
        
        # Filter out None values (signals with insufficient forward data)
        valid_signals = [s for s in self.signal_history if s is not None]
        
        if not valid_signals:
            return {"total_signals": 0, "excluded_signals": len(self.signal_history)}
        
        buy_signals = [s for s in valid_signals if s.signal_type == "BUY"]
        sell_signals = [s for s in valid_signals if s.signal_type == "SELL"]
        
        metrics = {
            "total_signals": len(valid_signals),
            "excluded_signals": len(self.signal_history) - len(valid_signals),
            "buy_signals": len(buy_signals),
            "sell_signals": len(sell_signals)
        }
        
        if buy_signals:
            # Profitability metrics
            profitable_3d = sum(1 for s in buy_signals if s.is_profitable_3d)
            profitable_5d = sum(1 for s in buy_signals if s.is_profitable_5d)
            
            # Return metrics
            avg_return_3d = sum(s.return_3d for s in buy_signals) / len(buy_signals)
            avg_return_5d = sum(s.return_5d for s in buy_signals) / len(buy_signals)
            avg_return_7d = sum(s.return_7d for s in buy_signals) / len(buy_signals)
            
            # Risk metrics
            avg_mae = sum(s.max_adverse_excursion for s in buy_signals) / len(buy_signals)
            avg_mfe = sum(s.max_favorable_excursion for s in buy_signals) / len(buy_signals)
            
            # Bounce success
            bounce_success = sum(1 for s in buy_signals if s.bounce_successful)
            bounce_success_rate = bounce_success / len(buy_signals)
            
            # Win/Loss distribution
            wins = [s for s in buy_signals if s.return_5d > 0]
            losses = [s for s in buy_signals if s.return_5d < 0]
            
            avg_win = sum(s.return_5d for s in wins) / len(wins) if wins else 0
            avg_loss = sum(s.return_5d for s in losses) / len(losses) if losses else 0
            
            # Expectancy calculation
            win_rate = len(wins) / len(buy_signals)
            loss_rate = len(losses) / len(buy_signals)
            expectancy_5d = (win_rate * avg_win) - (loss_rate * abs(avg_loss))
            
            metrics.update({
                "profitable_3d_pct": (profitable_3d / len(buy_signals)) * 100,
                "profitable_5d_pct": (profitable_5d / len(buy_signals)) * 100,
                "avg_return_3d": avg_return_3d * 100,
                "avg_return_5d": avg_return_5d * 100,
                "avg_return_7d": avg_return_7d * 100,
                "avg_mae_pct": avg_mae * 100,
                "avg_mfe_pct": avg_mfe * 100,
                "bounce_success_rate": bounce_success_rate * 100,
                "win_rate_pct": win_rate * 100,
                "avg_win_pct": avg_win * 100,
                "avg_loss_pct": avg_loss * 100,
                "expectancy_5d": expectancy_5d * 100,
                "total_wins": len(wins),
                "total_losses": len(losses)
            })
        
        return metrics

# Integration with existing SignalCalculator
class EnhancedSignalCalculator:
    """Enhanced signal calculator with forward return validation"""
    
    def __init__(self, config, price_data: pd.DataFrame):
        self.config = config
        self.validator = SignalQualityValidator(price_data)
    
    def calculate_signal_with_validation(self, conditions: MarketConditions, 
                                      symbol: str, current_date: str) -> tuple:
        """Calculate signal and validate forward returns if historical data available"""
        
        # Generate signal using existing logic
        signal_result = self.calculate_signal(conditions, symbol)
        
        # If we have historical data, validate forward returns
        if current_date and self.validator.price_data.index.min() < pd.to_datetime(current_date):
            validation_metrics = self.validator.calculate_forward_returns(
                current_date, 
                conditions.current_price,
                signal_result.signal.value,
                conditions.rsi,
                conditions.volatility
            )
            
            return signal_result, validation_metrics
        
        return signal_result, None
