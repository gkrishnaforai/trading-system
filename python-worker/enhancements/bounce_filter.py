"""
Failed Bounce Filter Enhancement
Avoid catching falling knives by requiring bounce confirmation
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import pandas as pd
import numpy as np
import sys
import os
sys.path.append('/app')
from app.signal_engines.signal_calculator_core import MarketConditions, SignalConfig, SignalResult, SignalType

@dataclass
class BounceAnalysis:
    """Analysis of price bounce patterns"""
    is_bouncing: bool
    bounce_strength: float  # 0-1 scale
    lower_lows_stopped: bool
    macd_improving: bool
    volume_confirmation: bool
    price_action_score: float

class BounceFilter:
    """Filters out signals that are likely to catch falling knives"""
    
    def __init__(self, price_data: pd.DataFrame):
        self.price_data = price_data.set_index('date')
    
    def analyze_bounce_potential(self, current_date: str, rsi: float, 
                                macd: float, macd_signal: float) -> BounceAnalysis:
        """Analyze if price is showing bounce characteristics"""
        
        try:
            current_idx = self.price_data.index.get_loc(pd.to_datetime(current_date).date())
            
            # Need at least 10 days of history for analysis
            if current_idx < 10:
                return BounceAnalysis(False, 0.0, False, False, False, 0.0)
            
            # 1. Check if lower lows have stopped
            lower_lows_stopped = self._check_lower_lows_stopped(current_idx)
            
            # 2. Check MACD improvement
            macd_improving = self._check_macd_improvement(current_idx, macd, macd_signal)
            
            # 3. Check volume confirmation
            volume_confirmation = self._check_volume_confirmation(current_idx)
            
            # 4. Price action scoring
            price_action_score = self._calculate_price_action_score(current_idx)
            
            # 5. Overall bounce strength
            bounce_strength = self._calculate_bounce_strength(
                rsi, lower_lows_stopped, macd_improving, 
                volume_confirmation, price_action_score
            )
            
            # Final bounce decision
            is_bouncing = (
                bounce_strength > 0.6 and  # Overall strength
                lower_lows_stopped and     # Must stop making lower lows
                (macd_improving or volume_confirmation)  # Need some confirmation
            )
            
            return BounceAnalysis(
                is_bouncing=is_bouncing,
                bounce_strength=bounce_strength,
                lower_lows_stopped=lower_lows_stopped,
                macd_improving=macd_improving,
                volume_confirmation=volume_confirmation,
                price_action_score=price_action_score
            )
            
        except (KeyError, IndexError):
            return BounceAnalysis(False, 0.0, False, False, False, 0.0)
    
    def _check_lower_lows_stopped(self, current_idx: int) -> bool:
        """Check if price has stopped making lower lows"""
        
        # Look at last 5 days of lows
        recent_data = self.price_data.iloc[max(0, current_idx-5):current_idx+1]
        lows = recent_data['low'].values
        
        if len(lows) < 3:
            return False
        
        # Check if the most recent low is higher than previous lows
        recent_low = lows[-1]
        previous_lows = lows[:-1]
        
        # Stop making lower lows if recent low is higher than most previous lows
        higher_than_previous = sum(1 for low in previous_lows if recent_low > low)
        return higher_than_previous >= len(previous_lows) * 0.6  # 60% threshold
    
    def _check_macd_improvement(self, current_idx: int, current_macd: float, 
                              current_macd_signal: float) -> bool:
        """Check if MACD is showing improvement"""
        
        if current_idx < 5:
            return False
        
        # Look at MACD trend over last 5 days
        recent_data = self.price_data.iloc[current_idx-5:current_idx+1]
        
        # Calculate MACD histogram trend
        macd_values = recent_data.get('macd', [0] * len(recent_data))
        signal_values = recent_data.get('macd_signal', [0] * len(recent_data))
        
        if len(macd_values) < 3:
            return False
        
        # Check if MACD histogram is improving (less negative or more positive)
        histograms = [m - s for m, s in zip(macd_values, signal_values)]
        
        # Improving if histogram trend is upward
        recent_histograms = histograms[-3:]
        return recent_histograms[-1] > recent_histograms[0]
    
    def _check_volume_confirmation(self, current_idx: int) -> bool:
        """Check if volume supports bounce"""
        
        if current_idx < 5:
            return False
        
        recent_data = self.price_data.iloc[current_idx-5:current_idx+1]
        volumes = recent_data['volume'].values
        
        if len(volumes) < 2:
            return False
        
        # Volume confirmation if recent volume is above average
        avg_volume = volumes[:-1].mean()
        recent_volume = volumes[-1]
        
        return recent_volume > avg_volume * 1.2  # 20% above average
    
    def _calculate_price_action_score(self, current_idx: int) -> float:
        """Calculate price action score (0-1)"""
        
        if current_idx < 10:
            return 0.0
        
        recent_data = self.price_data.iloc[current_idx-10:current_idx+1]
        
        # Multiple price action factors
        score = 0.0
        
        # 1. Price above recent low (avoid absolute bottom)
        recent_low = recent_data['low'].min()
        current_price = recent_data.iloc[-1]['close']
        if current_price > recent_low * 1.02:  # 2% above recent low
            score += 0.3
        
        # 2. Recent price stabilization
        closes = recent_data['close'].values
        if len(closes) >= 3:
            recent_volatility = closes[-3:].std() / closes[-3:].mean()
            overall_volatility = closes.std() / closes.mean()
            if recent_volatility < overall_volatility:  # Stabilizing
                score += 0.3
        
        # 3. Higher highs formation
        if len(closes) >= 5:
            recent_highs = closes[-3:]
            earlier_highs = closes[-5:-2]
            if max(recent_highs) > max(earlier_highs):
                score += 0.4
        
        return min(score, 1.0)
    
    def _calculate_bounce_strength(self, rsi: float, lower_lows_stopped: bool,
                                 macd_improving: bool, volume_confirmation: bool,
                                 price_action_score: float) -> float:
        """Calculate overall bounce strength (0-1)"""
        
        strength = 0.0
        
        # RSI contribution (oversold is good for bounce)
        if rsi < 30:
            strength += 0.3
        elif rsi < 35:
            strength += 0.2
        elif rsi < 40:
            strength += 0.1
        
        # Lower lows stopped (critical)
        if lower_lows_stopped:
            strength += 0.3
        
        # MACD improvement
        if macd_improving:
            strength += 0.2
        
        # Volume confirmation
        if volume_confirmation:
            strength += 0.1
        
        # Price action score
        strength += price_action_score * 0.1
        
        return min(strength, 1.0)
    
    def _detect_bounce(self, start_idx: int, entry_price: float, days_forward: int) -> bool:
        """Detect if price successfully bounced after BUY signal (less strict for TQQQ)"""
        
        if start_idx + days_forward >= len(self.price_data):
            return False
        
        forward_data = self.price_data.iloc[start_idx:start_idx + days_forward + 1]
        
        # More flexible bounce detection for TQQQ/leveraged ETFs
        lows = forward_data['low'].values
        entry_low = forward_data.iloc[0]['low']
        
        # Allow 1 marginal lower low (more realistic for volatile ETFs)
        marginal_lower_lows = sum(1 for low in lows[1:] if low < entry_low)
        
        # Allow up to 0.5% tolerance for lower lows (TQQQ specific)
        tolerance = entry_low * 0.005  # 0.5% tolerance
        significant_lower_lows = sum(1 for low in lows[1:] if low < entry_low - tolerance)
        
        # At least 60% of days are at or above entry low
        at_or_above_entry = sum(1 for low in lows if low >= entry_low - tolerance)
        above_threshold = at_or_above_entry / len(lows) >= 0.6
        
        # Successful bounce if:
        # 1. No more than 1 marginal lower low, AND
        # 2. No significant lower lows (>0.5% below entry), AND
        # 3. At least 60% of days are at or above entry low
        return marginal_lower_lows <= 1 and significant_lower_lows == 0 and above_threshold

# Integration with existing signal logic
class BounceAwareSignalCalculator:
    """Signal calculator with bounce filtering"""
    
    def __init__(self, config, price_data: pd.DataFrame):
        self.config = config
        self.bounce_filter = BounceFilter(price_data)
    
    def calculate_signal_with_bounce_filter(self, conditions: MarketConditions, 
                                          symbol: str, current_date: str) -> tuple:
        """Calculate signal with bounce filtering for BUY signals"""
        
        # Generate base signal
        signal_result = self.calculate_signal(conditions, symbol)
        
        # Apply bounce filter to BUY signals
        if signal_result.signal.value == "BUY":
            bounce_analysis = self.bounce_filter.analyze_bounce_potential(
                current_date, conditions.rsi, conditions.macd, conditions.macd_signal
            )
            
            if not bounce_analysis.is_bouncing:
                # Convert to HOLD with bounce filter reasoning
                signal_result.signal = SignalType.HOLD
                signal_result.confidence = 0.1
                signal_result.reasoning = [
                    f"HOLD: Bounce filter failed",
                    f"Bounce strength: {bounce_analysis.bounce_strength:.2f}",
                    f"Lower lows stopped: {bounce_analysis.lower_lows_stopped}",
                    f"MACD improving: {bounce_analysis.macd_improving}",
                    f"Volume confirmation: {bounce_analysis.volume_confirmation}",
                    f"Price action score: {bounce_analysis.price_action_score:.2f}",
                    "Avoiding potential falling knife"
                ]
                signal_result.metadata["bounce_filter_applied"] = True
                signal_result.metadata["bounce_analysis"] = bounce_analysis
            else:
                # Enhance BUY signal with bounce confirmation
                signal_result.confidence = min(0.9, signal_result.confidence + 0.1)
                signal_result.reasoning.append(f"Bounce confirmed: {bounce_analysis.bounce_strength:.2f}")
                signal_result.metadata["bounce_filter_applied"] = True
                signal_result.metadata["bounce_analysis"] = bounce_analysis
        
        return signal_result
