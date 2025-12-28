"""
Entry/Exit Plan Calculator
Computes industry-standard entry and exit levels for position and swing trading
"""

from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

from app.observability.logging import get_logger

logger = get_logger(__name__)


class EntryExitCalculator:
    """Calculates entry/exit plans based on technical analysis"""
    
    def __init__(self):
        """Initialize entry/exit calculator"""
        pass
    
    def calculate_position_plan(
        self, 
        price_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        current_price: float
    ) -> Dict[str, Any]:
        """
        Calculate position trading plan (weeks to months)
        
        Args:
            price_data: Historical price data with OHLCV
            indicators: Technical indicators
            fundamentals: Fundamental data
            current_price: Current market price
            
        Returns:
            Position trading plan with entry/exit levels
        """
        try:
            plan = {
                "timeframe": "Position (Weeks to Months)",
                "bias": self._determine_bias(indicators, fundamentals),
                "entry": self._calculate_position_entry(price_data, indicators, current_price),
                "stops": self._calculate_position_stops(price_data, indicators),
                "targets": self._calculate_position_targets(price_data, indicators),
                "invalidation": self._calculate_position_invalidation(price_data, indicators),
                "risk_reward": None,
                "reasoning": []
            }
            
            # Calculate risk/reward ratios
            if plan["entry"]["price_range"] and plan["stops"]["levels"]:
                entry_mid = (plan["entry"]["price_range"][0] + plan["entry"]["price_range"][1]) / 2
                stop_level = plan["stops"]["levels"][0]["price"]
                target_level = plan["targets"]["levels"][0]["price"] if plan["targets"]["levels"] else None
                
                if stop_level and target_level:
                    risk = abs(entry_mid - stop_level)
                    reward = abs(target_level - entry_mid)
                    if risk > 0:
                        plan["risk_reward"] = f"1:{reward/risk:.1f}"
            
            return plan
            
        except Exception as e:
            logger.error(f"Error calculating position plan: {e}")
            return self._empty_plan("Position")
    
    def calculate_swing_plan(
        self, 
        price_data: pd.DataFrame,
        indicators: Dict[str, Any],
        current_price: float
    ) -> Dict[str, Any]:
        """
        Calculate swing trading plan (days to weeks)
        
        Args:
            price_data: Historical price data with OHLCV
            indicators: Technical indicators
            current_price: Current market price
            
        Returns:
            Swing trading plan with entry/exit levels
        """
        try:
            plan = {
                "timeframe": "Swing (Days to Weeks)",
                "bias": self._determine_swing_bias(indicators),
                "entry": self._calculate_swing_entry(price_data, indicators, current_price),
                "stops": self._calculate_swing_stops(price_data, indicators),
                "targets": self._calculate_swing_targets(price_data, indicators),
                "invalidation": self._calculate_swing_invalidation(price_data, indicators),
                "risk_reward": None,
                "reasoning": []
            }
            
            # Calculate risk/reward ratios
            if plan["entry"]["price"] and plan["stops"]["levels"] and plan["targets"]["levels"]:
                entry_price = plan["entry"]["price"]
                stop_level = plan["stops"]["levels"][0]["price"]
                target_level = plan["targets"]["levels"][0]["price"]
                
                risk = abs(entry_price - stop_level)
                reward = abs(target_level - entry_price)
                if risk > 0:
                    plan["risk_reward"] = f"1:{reward/risk:.1f}"
            
            return plan
            
        except Exception as e:
            logger.error(f"Error calculating swing plan: {e}")
            return self._empty_plan("Swing")
    
    def _determine_bias(self, indicators: Dict[str, Any], fundamentals: Dict[str, Any]) -> str:
        """Determine overall bias (bullish/bearish/neutral)"""
        bullish_signals = 0
        bearish_signals = 0
        
        # Technical signals
        if indicators.get("sma50") and indicators.get("sma200"):
            if indicators["sma50"] > indicators["sma200"]:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        if indicators.get("rsi"):
            rsi = indicators["rsi"]
            if rsi > 50:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        if indicators.get("macd_line") and indicators.get("macd_signal"):
            if indicators["macd_line"] > indicators["macd_signal"]:
                bullish_signals += 1
            else:
                bearish_signals += 1
        
        # Fundamental signals
        if fundamentals.get("pe_ratio"):
            pe = fundamentals["pe_ratio"]
            if 10 <= pe <= 25:  # Reasonable valuation
                bullish_signals += 1
            elif pe > 35:  # Overvalued
                bearish_signals += 1
        
        if fundamentals.get("debt_to_equity"):
            debt_ratio = fundamentals["debt_to_equity"]
            if debt_ratio < 0.5:  # Low debt
                bullish_signals += 1
            elif debt_ratio > 1.0:  # High debt
                bearish_signals += 1
        
        if bullish_signals > bearish_signals:
            return "Bullish"
        elif bearish_signals > bullish_signals:
            return "Bearish"
        else:
            return "Neutral"
    
    def _calculate_position_entry(self, price_data: pd.DataFrame, indicators: Dict[str, Any], current_price: float) -> Dict[str, Any]:
        """Calculate position entry zone"""
        entry_zone = []
        entry_conditions = []
        
        # Use EMA20 as dynamic support in uptrend
        if indicators.get("ema20"):
            ema20 = indicators["ema20"]
            if current_price > ema20:  # Price above support
                # Entry zone: 1-2% below current price towards EMA20
                zone_low = max(ema20 * 0.98, current_price * 0.98)
                zone_high = current_price * 0.99
                entry_zone = [round(zone_low, 2), round(zone_high, 2)]
                entry_conditions.append("Pullback to EMA20 support")
                entry_conditions.append("Price above key moving averages")
        
        # If no clear support, use recent consolidation
        if not entry_zone and len(price_data) >= 20:
            recent_prices = price_data.tail(20)['close']
            consolidation_low = recent_prices.min()
            consolidation_high = recent_prices.max()
            
            if current_price < consolidation_high * 0.95:  # Near bottom of range
                entry_zone = [round(consolidation_low * 0.98, 2), round(consolidation_high * 0.95, 2)]
                entry_conditions.append("Near consolidation support")
        
        return {
            "price_range": entry_zone,
            "conditions": entry_conditions,
            "relative_guidance": "Wait for pullback to support levels in established uptrend"
        }
    
    def _calculate_position_stops(self, price_data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate position stop levels by risk"""
        stops = {"levels": [], "reasoning": []}
        
        if len(price_data) < 50:
            return stops
        
        # Conservative stop (low risk) - below SMA200
        if indicators.get("sma200"):
            stops["levels"].append({
                "price": round(indicators["sma200"] * 0.95, 2),
                "risk_level": "Low",
                "type": "Conservative (SMA200)"
            })
            stops["reasoning"].append("Below long-term trend support")
        
        # Medium risk stop - below recent swing low
        recent_low = price_data.tail(50)['low'].min()
        stops["levels"].append({
            "price": round(recent_low * 0.98, 2),
            "risk_level": "Medium", 
            "type": "Swing Low"
        })
        stops["reasoning"].append("Below recent swing low")
        
        # High risk stop - tighter stop below EMA20
        if indicators.get("ema20"):
            stops["levels"].append({
                "price": round(indicators["ema20"] * 0.97, 2),
                "risk_level": "High",
                "type": "Tight (EMA20)"
            })
            stops["reasoning"].append("Tight stop below immediate support")
        
        return stops
    
    def _calculate_position_targets(self, price_data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate position target levels"""
        targets = {"levels": [], "reasoning": []}
        
        if len(price_data) < 50:
            return targets
        
        current_price = price_data.iloc[-1]['close']
        
        # Target 1: Recent resistance
        recent_high = price_data.tail(50)['high'].max()
        if recent_high > current_price:
            targets["levels"].append({
                "price": round(recent_high, 2),
                "type": "Recent Resistance"
            })
            targets["reasoning"].append("Test recent resistance level")
        
        # Target 2: Extension based on volatility
        atr = indicators.get("atr")
        if atr:
            volatility_target = current_price + (atr * 3)  # 3x ATR extension
            targets["levels"].append({
                "price": round(volatility_target, 2),
                "type": "Volatility Extension"
            })
            targets["reasoning"].append("3x ATR extension from current price")
        
        return targets
    
    def _calculate_position_invalidation(self, price_data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate position invalidation levels"""
        invalidation = {
            "price_levels": [],
            "conditions": [],
            "reasoning": "Position invalidated if price closes below key support levels"
        }
        
        # Key invalidation: close below SMA200
        if indicators.get("sma200"):
            invalidation["price_levels"].append({
                "price": round(indicators["sma200"], 2),
                "condition": "Close below SMA200"
            })
            invalidation["conditions"].append("Long-term trend broken")
        
        # Secondary: break below recent consolidation
        if len(price_data) >= 20:
            consolidation_low = price_data.tail(20)['low'].min()
            invalidation["price_levels"].append({
                "price": round(consolidation_low, 2),
                "condition": "Break consolidation low"
            })
            invalidation["conditions"].append("Support structure broken")
        
        return invalidation
    
    def _determine_swing_bias(self, indicators: Dict[str, Any]) -> str:
        """Determine swing trading bias"""
        signals = 0
        
        # Short-term momentum
        if indicators.get("rsi"):
            rsi = indicators["rsi"]
            if 40 <= rsi <= 60:
                signals += 0  # Neutral
            elif rsi > 60:
                signals += 1  # Bullish
            else:
                signals -= 1  # Bearish
        
        # MACD momentum
        if indicators.get("macd_line") and indicators.get("macd_signal"):
            if indicators["macd_line"] > indicators["macd_signal"]:
                signals += 1
            else:
                signals -= 1
        
        if signals > 0:
            return "Bullish"
        elif signals < 0:
            return "Bearish"
        else:
            return "Neutral"
    
    def _calculate_swing_entry(self, price_data: pd.DataFrame, indicators: Dict[str, Any], current_price: float) -> Dict[str, Any]:
        """Calculate swing entry point"""
        entry = {
            "price": None,
            "conditions": [],
            "relative_guidance": "Enter on breakout or pullback confirmation"
        }
        
        if len(price_data) < 10:
            return entry
        
        # Look for breakout above recent resistance
        recent_high = price_data.tail(10)['high'].max()
        if current_price > recent_high * 0.98:  # Near breakout
            entry["price"] = round(recent_high * 1.01, 2)  # Slightly above resistance
            entry["conditions"].append("Breakout above recent high")
        
        # Or pullback to EMA20
        elif indicators.get("ema20") and current_price > indicators["ema20"]:
            entry["price"] = round(indicators["ema20"] * 1.01, 2)
            entry["conditions"].append("Pullback to EMA20 support")
        
        return entry
    
    def _calculate_swing_stops(self, price_data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate swing stop levels"""
        stops = {"levels": [], "reasoning": []}
        
        if len(price_data) < 5:
            return stops
        
        # Conservative: 2-day low
        two_day_low = price_data.tail(2)['low'].min()
        stops["levels"].append({
            "price": round(two_day_low * 0.99, 2),
            "risk_level": "Low",
            "type": "2-Day Low"
        })
        stops["reasoning"].append("Below recent swing low")
        
        # Medium: ATR-based stop
        atr = indicators.get("atr")
        current_price = price_data.iloc[-1]['close']
        if atr and current_price:
            atr_stop = current_price - (atr * 1.5)  # 1.5x ATR stop
            stops["levels"].append({
                "price": round(atr_stop, 2),
                "risk_level": "Medium",
                "type": "ATR-based (1.5x)"
            })
            stops["reasoning"].append("Volatility-based stop")
        
        return stops
    
    def _calculate_swing_targets(self, price_data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate swing target levels"""
        targets = {"levels": [], "reasoning": []}
        
        if len(price_data) < 10:
            return targets
        
        current_price = price_data.iloc[-1]['close']
        
        # Target: Next resistance level
        recent_high = price_data.tail(10)['high'].max()
        if recent_high > current_price:
            targets["levels"].append({
                "price": round(recent_high, 2),
                "type": "Near-term Resistance"
            })
            targets["reasoning"].append("Test recent resistance")
        
        # Risk-based target: 2x risk
        atr = indicators.get("atr")
        if atr:
            risk_target = current_price + (atr * 3)  # 3x ATR for 2:1 RR
            targets["levels"].append({
                "price": round(risk_target, 2),
                "type": "Risk-based (2:1)"
            })
            targets["reasoning"].append("2:1 risk/reward target")
        
        return targets
    
    def _calculate_swing_invalidation(self, price_data: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate swing invalidation levels"""
        invalidation = {
            "price_levels": [],
            "conditions": [],
            "reasoning": "Swing trade invalidated if price breaks key support"
        }
        
        # Break below recent low
        if len(price_data) >= 5:
            recent_low = price_data.tail(5)['low'].min()
            invalidation["price_levels"].append({
                "price": round(recent_low, 2),
                "condition": "Break 5-day low"
            })
            invalidation["conditions"].append("Short-term structure broken")
        
        return invalidation
    
    def _empty_plan(self, timeframe: str) -> Dict[str, Any]:
        """Return empty plan structure"""
        return {
            "timeframe": timeframe,
            "bias": "Neutral",
            "entry": {"price_range": None, "conditions": ["Insufficient data"], "relative_guidance": "Wait for more data"},
            "stops": {"levels": [], "reasoning": []},
            "targets": {"levels": [], "reasoning": []},
            "invalidation": {"price_levels": [], "conditions": [], "reasoning": "Insufficient data"},
            "risk_reward": None,
            "reasoning": ["Insufficient data to calculate plan"]
        }
