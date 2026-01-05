"""
Specialized Swing Engines Architecture
Split into focused engines for different swing strategies
"""

from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import sys
import os
sys.path.append('/app')
from app.signal_engines.signal_calculator_core import SignalType, MarketConditions, SignalConfig, SignalResult

class SwingEngineType(Enum):
    MEAN_REVERSION = "mean_reversion"
    TREND_PULLBACK = "trend_pullback"
    MOMENTUM_CONTINUATION = "momentum_continuation"
    VOLATILITY_KILL_SWITCH = "volatility_kill_switch"

@dataclass
class EngineOutput:
    """Output from specialized swing engine"""
    signal: SignalType
    confidence: float
    reasoning: List[str]
    engine_type: SwingEngineType
    engine_specific_data: Dict

class BaseSwingEngine(ABC):
    """Base class for specialized swing engines"""
    
    def __init__(self, config: SignalConfig, engine_type: SwingEngineType):
        self.config = config
        self.engine_type = engine_type
    
    @abstractmethod
    def should_generate_signal(self, conditions: MarketConditions) -> bool:
        """Check if this engine should generate a signal for current conditions"""
        pass
    
    @abstractmethod
    def generate_signal_logic(self, conditions: MarketConditions) -> SignalResult:
        """Generate signal using engine-specific logic"""
        pass
    
    def process(self, conditions: MarketConditions, symbol: str) -> Optional[EngineOutput]:
        """Process market conditions and generate signal if applicable"""
        
        if not self.should_generate_signal(conditions):
            return None
        
        signal_result = self.generate_signal_logic(conditions)
        
        return EngineOutput(
            signal=signal_result.signal,
            confidence=signal_result.confidence,
            reasoning=signal_result.reasoning,
            engine_type=self.engine_type,
            engine_specific_data=signal_result.metadata
        )

class MeanReversionEngine(BaseSwingEngine):
    """Specialized engine for mean reversion signals"""
    
    def __init__(self, config: SignalConfig):
        super().__init__(config, SwingEngineType.MEAN_REVERSION)
    
    def should_generate_signal(self, conditions: MarketConditions) -> bool:
        """Mean reversion works best in range-bound or high volatility markets"""
        
        # Check if oversold conditions exist
        is_oversold = conditions.rsi < self.config.rsi_oversold
        is_moderately_oversold = conditions.rsi < self.config.rsi_moderately_oversold
        
        # Mean reversion works when:
        # 1. Oversold conditions exist
        # 2. Not in strong uptrend (avoid buying dips in strong uptrends)
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        
        return (is_oversold or is_moderately_oversold) and not is_uptrend
    
    def generate_signal_logic(self, conditions: MarketConditions) -> SignalResult:
        """Generate mean reversion signal"""
        
        is_oversold = conditions.rsi < self.config.rsi_oversold
        is_moderately_oversold = conditions.rsi < self.config.rsi_moderately_oversold
        is_recently_down = conditions.recent_change < -0.02
        
        reasoning = []
        confidence = 0.5
        
        if is_oversold and is_recently_down:
            signal = SignalType.BUY
            confidence = 0.7
            reasoning.extend([
                "Mean reversion: Strong oversold",
                f"RSI oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Expect bounce to mean"
            ])
        elif is_oversold:
            signal = SignalType.BUY
            confidence = 0.6
            reasoning.extend([
                "Mean reversion: Oversold stabilization",
                f"RSI oversold: {conditions.rsi:.1f}",
                "Bottoming pattern",
                "Mean reversion entry"
            ])
        elif is_moderately_oversold and not is_recently_down:
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Mean reversion: Moderate oversold",
                f"RSI moderately oversold: {conditions.rsi:.1f}",
                "Support level",
                "Reversal potential"
            ])
        else:
            signal = SignalType.HOLD
            confidence = 0.2
            reasoning.extend([
                "Mean reversion: No clear setup",
                f"RSI neutral: {conditions.rsi:.1f}",
                "Wait for oversold"
            ])
        
        metadata = {
            "engine": "mean_reversion",
            "oversold_level": "strong" if is_oversold else "moderate" if is_moderately_oversold else "none",
            "mean_reversion_strength": confidence
        }
        
        return SignalResult(signal, confidence, reasoning, metadata)

class TrendPullbackEngine(BaseSwingEngine):
    """Specialized engine for trend pullback signals"""
    
    def __init__(self, config: SignalConfig):
        super().__init__(config, SwingEngineType.TREND_PULLBACK)
    
    def should_generate_signal(self, conditions: MarketConditions) -> bool:
        """Trend pullback works only in established uptrends"""
        
        # Must be in clear uptrend
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        
        # Must have some pullback (mild oversold or recent decline)
        is_mildly_oversold = conditions.rsi < self.config.rsi_mildly_oversold
        is_recently_down = conditions.recent_change < -0.01
        
        return is_uptrend and (is_mildly_oversold or is_recently_down)
    
    def generate_signal_logic(self, conditions: MarketConditions) -> SignalResult:
        """Generate trend pullback signal"""
        
        is_mildly_oversold = conditions.rsi < self.config.rsi_mildly_oversold
        is_recently_down = conditions.recent_change < -0.01
        macd_bullish = conditions.macd > conditions.macd_signal
        
        reasoning = []
        confidence = 0.5
        
        if is_mildly_oversold and macd_bullish:
            signal = SignalType.BUY
            confidence = 0.6
            reasoning.extend([
                "Trend pullback: Dip with MACD confirmation",
                f"RSI mildly oversold: {conditions.rsi:.1f}",
                "Uptrend support",
                "MACD bullish",
                "Buy the dip"
            ])
        elif is_mildly_oversold:
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Trend pullback: Mild dip",
                f"RSI mildly oversold: {conditions.rsi:.1f}",
                "Uptrend continuation expected",
                "Conservative entry"
            ])
        elif is_recently_down and macd_bullish:
            signal = SignalType.BUY
            confidence = 0.4
            reasoning.extend([
                "Trend pullback: Recent decline",
                f"Recent decline: {conditions.recent_change:.2%}",
                "MACD bullish confirmation",
                "Trend-following entry"
            ])
        else:
            signal = SignalType.HOLD
            confidence = 0.2
            reasoning.extend([
                "Trend pullback: No clear setup",
                f"RSI neutral: {conditions.rsi:.1f}",
                "Wait for pullback"
            ])
        
        metadata = {
            "engine": "trend_pullback",
            "pullback_type": "oversold" if is_mildly_oversold else "decline",
            "trend_strength": confidence
        }
        
        return SignalResult(signal, confidence, reasoning, metadata)

class MomentumContinuationEngine(BaseSwingEngine):
    """Specialized engine for momentum continuation signals"""
    
    def __init__(self, config: SignalConfig):
        super().__init__(config, SwingEngineType.MOMENTUM_CONTINUATION)
    
    def should_generate_signal(self, conditions: MarketConditions) -> bool:
        """Momentum continuation works in strong trends with momentum"""
        
        # Must be in trend (up or down)
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        is_downtrend = conditions.sma_20 < conditions.sma_50 and conditions.current_price < conditions.sma_20
        
        # Must have momentum confirmation
        macd_bullish = conditions.macd > conditions.macd_signal
        macd_bearish = conditions.macd < conditions.macd_signal
        
        return (is_uptrend and macd_bullish) or (is_downtrend and macd_bearish)
    
    def generate_signal_logic(self, conditions: MarketConditions) -> SignalResult:
        """Generate momentum continuation signal"""
        
        is_uptrend = conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20
        is_downtrend = conditions.sma_20 < conditions.sma_50 and conditions.current_price < conditions.sma_20
        macd_bullish = conditions.macd > conditions.macd_signal
        macd_bearish = conditions.macd < conditions.macd_signal
        
        is_overbought = conditions.rsi > self.config.rsi_overbought
        is_oversold = conditions.rsi < self.config.rsi_oversold
        
        reasoning = []
        confidence = 0.5
        
        if is_uptrend and macd_bullish and not is_overbought:
            signal = SignalType.BUY
            confidence = 0.5
            reasoning.extend([
                "Momentum continuation: Uptrend",
                f"RSI strength: {conditions.rsi:.1f}",
                "MACD bullish",
                "Trend momentum",
                "Momentum entry"
            ])
        elif is_downtrend and macd_bearish and not is_oversold:
            signal = SignalType.SELL
            confidence = 0.5
            reasoning.extend([
                "Momentum continuation: Downtrend",
                f"RSI weakness: {conditions.rsi:.1f}",
                "MACD bearish",
                "Downtrend momentum",
                "Momentum exit"
            ])
        else:
            signal = SignalType.HOLD
            confidence = 0.2
            reasoning.extend([
                "Momentum continuation: No clear momentum",
                f"RSI neutral: {conditions.rsi:.1f}",
                "Wait for momentum setup"
            ])
        
        metadata = {
            "engine": "momentum_continuation",
            "momentum_direction": "bullish" if is_uptrend else "bearish" if is_downtrend else "neutral",
            "momentum_strength": confidence
        }
        
        return SignalResult(signal, confidence, reasoning, metadata)

class VolatilityKillSwitch(BaseSwingEngine):
    """Specialized engine that acts as a volatility filter"""
    
    def __init__(self, config: SignalConfig):
        super().__init__(config, SwingEngineType.VOLATILITY_KILL_SWITCH)
    
    def should_generate_signal(self, conditions: MarketConditions) -> bool:
        """Always check volatility"""
        return True
    
    def generate_signal_logic(self, conditions: MarketConditions) -> SignalResult:
        """Generate volatility-based HOLD signal"""
        
        if conditions.volatility > self.config.max_volatility:
            return SignalResult(
                signal=SignalType.HOLD,
                confidence=0.1,
                reasoning=[
                    "Volatility kill switch activated",
                    f"Volatility: {conditions.volatility:.1f}% > {self.config.max_volatility:.1f}%",
                    "Avoid trading in high volatility",
                    "Risk management override"
                ],
                metadata={
                    "engine": "volatility_kill_switch",
                    "volatility_level": conditions.volatility,
                    "kill_switch_active": True
                }
            )
        
        # Return neutral signal (no action needed)
        return SignalResult(
            signal=SignalType.HOLD,
            confidence=0.0,
            reasoning=["Volatility normal", "No action needed"],
            metadata={
                "engine": "volatility_kill_switch",
                "volatility_level": conditions.volatility,
                "kill_switch_active": False
            }
        )

class CompositeSwingEngine:
    """Composite engine that combines multiple specialized engines"""
    
    def __init__(self, config: SignalConfig, price_data: pd.DataFrame):
        self.config = config
        self.engines = [
            MeanReversionEngine(config),
            TrendPullbackEngine(config),
            MomentumContinuationEngine(config),
            VolatilityKillSwitch(config)
        ]
        self.engine_weights = {
            SwingEngineType.MEAN_REVERSION: 0.4,
            SwingEngineType.TREND_PULLBACK: 0.3,
            SwingEngineType.MOMENTUM_CONTINUATION: 0.3,
            SwingEngineType.VOLATILITY_KILL_SWITCH: 1.0  # Override if activated
        }
    
    def generate_composite_signal(self, conditions: MarketConditions, 
                                symbol: str, current_date: str) -> SignalResult:
        """Generate composite signal from all engines"""
        
        engine_outputs = []
        
        # Process all engines
        for engine in self.engines:
            output = engine.process(conditions, symbol)
            if output:
                engine_outputs.append(output)
        
        # Check volatility kill switch first (highest priority)
        volatility_output = next((o for o in engine_outputs 
                               if o.engine_type == SwingEngineType.VOLATILITY_KILL_SWITCH 
                               and o.metadata.get("kill_switch_active")), None)
        
        if volatility_output:
            return SignalResult(
                signal=volatility_output.signal,
                confidence=volatility_output.confidence,
                reasoning=volatility_output.reasoning,
                metadata={
                    "composite_engine": True,
                    "active_engines": [o.engine_type.value for o in engine_outputs],
                    "volatile_override": True,
                    "volatility_level": volatility_output.metadata["volatility_level"]
                }
            )
        
        # Combine signals from other engines
        buy_signals = [o for o in engine_outputs if o.signal == SignalType.BUY]
        sell_signals = [o for o in engine_outputs if o.signal == SignalType.SELL]
        
        # Weighted voting
        buy_weight = sum(self.engine_weights[o.engine_type] for o in buy_signals)
        sell_weight = sum(self.engine_weights[o.engine_type] for o in sell_signals)
        
        # Determine final signal
        if buy_weight > sell_weight and buy_weight > 0.3:
            # Combine reasoning from BUY engines
            all_reasoning = []
            for output in buy_signals:
                all_reasoning.extend(output.reasoning)
            
            # Weight confidence
            avg_confidence = sum(o.confidence * self.engine_weights[o.engine_type] 
                              for o in buy_signals) / buy_weight
            
            return SignalResult(
                signal=SignalType.BUY,
                confidence=avg_confidence,
                reasoning=all_reasoning[:5],  # Top 5 reasons
                metadata={
                    "composite_engine": True,
                    "active_engines": [o.engine_type.value for o in buy_signals],
                    "buy_weight": buy_weight,
                    "sell_weight": sell_weight,
                    "engine_contributions": {o.engine_type.value: o.confidence for o in buy_signals}
                }
            )
        
        elif sell_weight > buy_weight and sell_weight > 0.3:
            # Similar logic for SELL signals
            all_reasoning = []
            for output in sell_signals:
                all_reasoning.extend(output.reasoning)
            
            avg_confidence = sum(o.confidence * self.engine_weights[o.engine_type] 
                              for o in sell_signals) / sell_weight
            
            return SignalResult(
                signal=SignalType.SELL,
                confidence=avg_confidence,
                reasoning=all_reasoning[:5],
                metadata={
                    "composite_engine": True,
                    "active_engines": [o.engine_type.value for o in sell_signals],
                    "buy_weight": buy_weight,
                    "sell_weight": sell_weight,
                    "engine_contributions": {o.engine_type.value: o.confidence for o in sell_signals}
                }
            )
        
        else:
            # HOLD signal
            return SignalResult(
                signal=SignalType.HOLD,
                confidence=0.2,
                reasoning=["No consensus signal", "Multiple engines inactive"],
                metadata={
                    "composite_engine": True,
                    "active_engines": [o.engine_type.value for o in engine_outputs],
                    "buy_weight": buy_weight,
                    "sell_weight": sell_weight,
                    "no_consensus": True
                }
            )
