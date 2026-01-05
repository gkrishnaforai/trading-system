#!/usr/bin/env python3
"""
Universal Fear/Greed Engine - DRY Implementation

This engine is completely asset-agnostic and can be used across:
- ETFs (TQQQ, SPY, QQQ)
- Stocks (NVDA, GOOGL, AAPL)
- Crypto (BTC, ETH)
- Commodities (GLD, OIL)

Key Principles:
1. Single Source of Truth for Fear/Greed logic
2. Asset-specific configurations via factory pattern
3. Universal scoring system (-100 to +100)
4. DRY - No duplicated logic across assets
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List, Union
import numpy as np
from abc import ABC, abstractmethod
from app.observability.logging import get_logger

class FearGreedState(Enum):
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"

@dataclass
class MarketData:
    """Universal market data structure"""
    vix_level: float = 20.0
    volatility: float = 3.0
    rsi: float = 50.0
    price: float = 0.0
    sma20: float = 0.0
    sma50: float = 0.0
    volume: float = 0.0
    avg_volume: float = 0.0
    volatility_trend: str = "stable"  # 'rising', 'falling', 'stable'
    days_above_rsi_70: int = 0
    trend_strength: float = 0.5  # 0-1
    asset_type: str = "universal"

@dataclass
class FearGreedAnalysis:
    """Universal fear/greed analysis result"""
    state: FearGreedState
    confidence: float
    raw_score: float  # -100 to +100 scale
    signal_bias: str  # "strongly_bullish", "bullish", "neutral", "bearish", "strongly_bearish"
    reasoning: List[str] = field(default_factory=list)
    
    # Universal risk parameters
    risk_adjustment: float = 1.0  # Position size multiplier
    confidence_adjustment: float = 0.0  # Confidence modifier
    stop_loss_adjustment: float = 1.0  # Stop loss multiplier
    
    # Asset-specific adjustments (filled by respective engines)
    asset_specific_adjustments: Dict = field(default_factory=dict)

class AssetConfiguration(ABC):
    """Abstract base class for asset-specific configurations"""
    
    @abstractmethod
    def get_thresholds(self) -> Dict[str, float]:
        """Get asset-specific thresholds"""
        pass
    
    @abstractmethod
    def get_scoring_weights(self) -> Dict[str, float]:
        """Get asset-specific scoring weights"""
        pass
    
    @abstractmethod
    def get_hysteresis_params(self) -> Dict[str, Union[float, int]]:
        """Get asset-specific hysteresis parameters"""
        pass
    
    @abstractmethod
    def get_risk_multipliers(self) -> Dict[str, float]:
        """Get asset-specific risk multipliers"""
        pass

class ETFConfiguration(AssetConfiguration):
    """ETF-specific configuration"""
    
    def get_thresholds(self) -> Dict[str, float]:
        return {
            'vix_fear': 22.0,
            'vix_extreme_fear': 25.0,
            'volatility_fear': 5.0,  # Lower for ETFs
            'volatility_extreme_fear': 6.5,
            'rsi_extreme_fear': 40.0,
            'rsi_greed': 65.0,
            'rsi_extreme_greed': 70.0,
        }
    
    def get_scoring_weights(self) -> Dict[str, float]:
        return {
            'vix_weight': 0.35,      # Higher weight for VIX in ETFs
            'volatility_weight': 0.25,
            'rsi_weight': 0.25,
            'price_position_weight': 0.15,
        }
    
    def get_hysteresis_params(self) -> Dict[str, Union[float, int]]:
        return {
            'entry_multiplier': 1.05,  # Less sensitive for ETFs
            'exit_multiplier': 0.95,
            'min_duration': 3,        # Longer duration for ETFs
        }
    
    def get_risk_multipliers(self) -> Dict[str, float]:
        return {
            'extreme_fear_size': 1.3,  # More conservative for ETFs
            'fear_size': 1.1,
            'greed_size': 0.9,
            'extreme_greed_size': 0.7,
        }

class StockConfiguration(AssetConfiguration):
    """Stock-specific configuration"""
    
    def get_thresholds(self) -> Dict[str, float]:
        return {
            'vix_fear': 22.0,
            'vix_extreme_fear': 25.0,
            'volatility_fear': 6.0,  # Standard for stocks
            'volatility_extreme_fear': 7.5,
            'rsi_extreme_fear': 40.0,
            'rsi_greed': 65.0,
            'rsi_extreme_greed': 70.0,
        }
    
    def get_scoring_weights(self) -> Dict[str, float]:
        return {
            'vix_weight': 0.30,
            'volatility_weight': 0.25,
            'rsi_weight': 0.25,
            'price_position_weight': 0.20,
        }
    
    def get_hysteresis_params(self) -> Dict[str, Union[float, int]]:
        return {
            'entry_multiplier': 1.10,
            'exit_multiplier': 0.90,
            'min_duration': 2,
        }
    
    def get_risk_multipliers(self) -> Dict[str, float]:
        return {
            'extreme_fear_size': 1.5,
            'fear_size': 1.2,
            'greed_size': 0.8,
            'extreme_greed_size': 0.5,
        }

class CryptoConfiguration(AssetConfiguration):
    """Crypto-specific configuration"""
    
    def get_thresholds(self) -> Dict[str, float]:
        return {
            'vix_fear': 20.0,  # Crypto is more volatile
            'vix_extreme_fear': 23.0,
            'volatility_fear': 8.0,  # Higher threshold for crypto
            'volatility_extreme_fear': 10.0,
            'rsi_extreme_fear': 35.0,  # Lower RSI threshold for crypto
            'rsi_greed': 70.0,  # Higher RSI threshold for crypto
            'rsi_extreme_greed': 75.0,
        }
    
    def get_scoring_weights(self) -> Dict[str, float]:
        return {
            'vix_weight': 0.25,      # Lower VIX weight for crypto
            'volatility_weight': 0.35,  # Higher volatility weight
            'rsi_weight': 0.25,
            'price_position_weight': 0.15,
        }
    
    def get_hysteresis_params(self) -> Dict[str, Union[float, int]]:
        return {
            'entry_multiplier': 1.15,  # More hysteresis for crypto
            'exit_multiplier': 0.85,
            'min_duration': 2,
        }
    
    def get_risk_multipliers(self) -> Dict[str, float]:
        return {
            'extreme_fear_size': 1.2,  # More conservative for crypto
            'fear_size': 1.0,
            'greed_size': 0.7,
            'extreme_greed_size': 0.4,
        }

class UniversalFearGreedEngine:
    """
    Universal Fear/Greed Engine - DRY Implementation
    
    Single engine that works across all asset types with asset-specific configurations.
    No duplicated logic - universal scoring and state detection.
    """
    
    def __init__(self, asset_config: AssetConfiguration, custom_overrides: Optional[Dict] = None):
        """
        Initialize with asset-specific configuration
        
        Args:
            asset_config: Asset-specific configuration object
            custom_overrides: Optional custom parameter overrides
        """
        self.config = asset_config
        self.logger = get_logger(__name__)
        
        # Apply custom overrides if provided
        if custom_overrides:
            self._apply_custom_overrides(custom_overrides)
        
        # State tracking
        self.current_state = FearGreedState.NEUTRAL
        self.state_duration = 0
        self.raw_score_history: List[float] = []
        
        # Cache configuration for performance
        self.thresholds = self.config.get_thresholds()
        self.scoring_weights = self.config.get_scoring_weights()
        self.hysteresis = self.config.get_hysteresis_params()
        self.risk_multipliers = self.config.get_risk_multipliers()
    
    def _apply_custom_overrides(self, overrides: Dict):
        """Apply custom parameter overrides"""
        # This allows for fine-tuning without breaking DRY principles
        pass  # Implementation would merge overrides with config
    
    def calculate_fear_greed_state(self, market_data: Union[Dict, MarketData]) -> FearGreedAnalysis:
        """
        Calculate fear/greed state - universal method for all assets
        
        Args:
            market_data: Market data as dict or MarketData object
            
        Returns:
            FearGreedAnalysis: Universal analysis result
        """
        
        try:
            # Convert dict to MarketData if needed
            if isinstance(market_data, dict):
                self.logger.info(f"🔍 Converting dict to MarketData: {market_data}")
                market_data = MarketData(**market_data)
            
            self.logger.info(f"📊 Fear/Greed input data: vix={market_data.vix_level}, vol={market_data.volatility}, rsi={market_data.rsi}, price={market_data.price}")
            
            # Calculate universal fear/greed score (-100 to +100)
            raw_score, score_components = self._calculate_universal_score(market_data)
            
            self.logger.info(f"🧮 Fear/Greed score calculation: raw_score={raw_score}, components={score_components}")
            
            # Determine state with hysteresis
            new_state = self._determine_state_with_hysteresis(raw_score)
            
            # Calculate confidence
            confidence = self._calculate_confidence(raw_score, score_components)
            
            # Generate reasoning
            reasoning = self._generate_reasoning(score_components, new_state)
            
            # Calculate signal bias and risk adjustments
            signal_bias = self._calculate_signal_bias(new_state, confidence)
            risk_adjustments = self._calculate_risk_adjustments(new_state, confidence)
            
            # Update state tracking
            self._update_state_tracking(new_state, raw_score)
            
            result = FearGreedAnalysis(
                state=new_state,
                confidence=confidence,
                raw_score=raw_score,
                signal_bias=signal_bias,
                reasoning=reasoning,
                **risk_adjustments
            )
            
            self.logger.info(f"✅ Fear/Greed result: state={result.state.value}, bias={result.signal_bias}, confidence={result.confidence}")
            
            return result
            
        except Exception as e:
            # Return neutral analysis on error
            return FearGreedAnalysis(
                state=FearGreedState.NEUTRAL,
                confidence=0.0,
                raw_score=0.0,
                signal_bias="neutral",
                reasoning=[f"Error in Fear/Greed calculation: {str(e)}"],
                position_size_multiplier=1.0,
                confidence_adjustment=0.0,
                stop_loss_adjustment=1.0
            )
    
    def _calculate_universal_score(self, data: MarketData) -> Tuple[float, Dict]:
        """
        Universal scoring system - same logic for all assets
        
        Returns:
            Tuple[float, Dict]: (raw_score, score_components)
        """
        
        components = {}
        
        # VIX component (-40 to +40)
        vix_score = self._calculate_vix_score(data.vix_level)
        components['vix_score'] = vix_score
        
        # Volatility component (-30 to +30)
        vol_score = self._calculate_volatility_score(data.volatility)
        components['volatility_score'] = vol_score
        
        # RSI component (-30 to +30)
        rsi_score = self._calculate_rsi_score(data.rsi)
        components['rsi_score'] = rsi_score
        
        # Price position component (-20 to +20)
        price_score = self._calculate_price_score(data.price, data.sma20)
        components['price_score'] = price_score
        
        # Calculate weighted total score
        total_score = (
            vix_score * self.scoring_weights['vix_weight'] +
            vol_score * self.scoring_weights['volatility_weight'] +
            rsi_score * self.scoring_weights['rsi_weight'] +
            price_score * self.scoring_weights['price_position_weight']
        )
        
        return total_score, components
    
    def _calculate_vix_score(self, vix: float) -> float:
        """Calculate VIX component score"""
        if vix >= self.thresholds['vix_extreme_fear']:
            return -40  # Extreme fear
        elif vix >= self.thresholds['vix_fear']:
            return -25  # Fear
        elif vix <= 15:  # Very low VIX = greed
            return 30
        elif vix <= 18:
            return 20
        else:
            return 0  # Neutral
    
    def _calculate_volatility_score(self, volatility: float) -> float:
        """Calculate volatility component score"""
        if volatility >= self.thresholds['volatility_extreme_fear']:
            return -30  # Extreme fear
        elif volatility >= self.thresholds['volatility_fear']:
            return -20  # Fear
        elif volatility <= 2:  # Very low volatility = greed
            return 25
        elif volatility <= 3:
            return 15
        else:
            return 0  # Neutral
    
    def _calculate_rsi_score(self, rsi: float) -> float:
        """Calculate RSI component score"""
        if rsi <= self.thresholds['rsi_extreme_fear']:
            return -30  # Extreme fear
        elif rsi <= 45:
            return -20  # Fear
        elif rsi >= self.thresholds['rsi_extreme_greed']:
            return 30  # Extreme greed
        elif rsi >= self.thresholds['rsi_greed']:
            return 20  # Greed
        else:
            return 0  # Neutral
    
    def _calculate_price_score(self, price: float, sma20: float) -> float:
        """Calculate price position component score"""
        if sma20 <= 0:
            return 0  # No SMA data
        
        price_vs_sma = (price - sma20) / sma20 * 100  # Percentage from SMA20
        
        if price_vs_sma <= -10:  # 10% below SMA20
            return -20  # Fear
        elif price_vs_sma <= -5:
            return -10  # Mild fear
        elif price_vs_sma >= 10:  # 10% above SMA20
            return 20  # Greed
        elif price_vs_sma >= 5:
            return 10  # Mild greed
        else:
            return 0  # Neutral
    
    def _determine_state_with_hysteresis(self, raw_score: float) -> FearGreedState:
        """Determine state with hysteresis - universal logic"""
        
        # Calculate effective thresholds with hysteresis
        if self.current_state == FearGreedState.NEUTRAL:
            # From neutral, need slightly stronger signal to enter extreme states
            # But not too strict - reduce entry multiplier for better responsiveness
            entry_mult = self.hysteresis.get('entry_multiplier', 1.05)  # Default to 1.05 if not set
            entry_mult = min(entry_mult, 1.05)  # Cap at 1.05 to prevent overly strict hysteresis
            
            extreme_fear_threshold = -40 * entry_mult
            fear_threshold = -20 * entry_mult
            greed_threshold = 20 * entry_mult
            extreme_greed_threshold = 40 * entry_mult
        else:
            extreme_fear_threshold = -40
            fear_threshold = -20
            greed_threshold = 20
            extreme_greed_threshold = 40
        
        # Apply minimum duration requirement (but allow first signal)
        if self.state_duration >= self.hysteresis.get('min_duration', 2):
            # If we've been in current state long enough, allow state change
            pass
        elif self.state_duration > 0:  # Not first signal, apply hysteresis
            return self.current_state
        # For first signal (duration = 0), allow state change
        
        self.logger.info(f"🎯 State determination: raw_score={raw_score:.2f}, thresholds={{extreme_fear:{extreme_fear_threshold:.2f}, fear:{fear_threshold:.2f}, greed:{greed_threshold:.2f}, extreme_greed:{extreme_greed_threshold:.2f}}}")
        
        # Determine new state
        if raw_score <= extreme_fear_threshold:
            return FearGreedState.EXTREME_FEAR
        elif raw_score <= fear_threshold:
            return FearGreedState.FEAR
        elif raw_score >= extreme_greed_threshold:
            return FearGreedState.EXTREME_GREED
        elif raw_score >= greed_threshold:
            return FearGreedState.GREED
        else:
            return FearGreedState.NEUTRAL
    
    def _calculate_confidence(self, raw_score: float, components: Dict) -> float:
        """Calculate confidence - universal logic"""
        
        # Base confidence from score magnitude
        score_magnitude = abs(raw_score)
        base_confidence = min(0.9, score_magnitude / 50)
        
        # Adjust based on component agreement
        component_values = list(components.values())
        positive_components = sum(1 for v in component_values if v > 0)
        negative_components = sum(1 for v in component_values if v < 0)
        
        total_components = len(component_values)
        
        if positive_components == total_components or negative_components == total_components:
            agreement_bonus = 0.1
        elif positive_components > 0 and negative_components > 0:
            agreement_bonus = -0.1
        else:
            agreement_bonus = 0.0
        
        confidence = max(0.1, min(0.95, base_confidence + agreement_bonus))
        return confidence
    
    def _generate_reasoning(self, components: Dict, state: FearGreedState) -> List[str]:
        """Generate reasoning - universal logic with asset-aware messages"""
        
        reasoning = []
        
        # Component-specific reasoning
        if components.get('vix_score', 0) <= -20:
            reasoning.append("High VIX indicates market fear")
        elif components.get('vix_score', 0) >= 10:
            reasoning.append("Low VIX indicates market complacency")
        
        if components.get('volatility_score', 0) <= -15:
            reasoning.append("High volatility suggests fear/uncertainty")
        elif components.get('volatility_score', 0) >= 10:
            reasoning.append("Low volatility suggests complacency")
        
        if components.get('rsi_score', 0) <= -15:
            reasoning.append("RSI indicates oversold conditions")
        elif components.get('rsi_score', 0) >= 15:
            reasoning.append("RSI indicates overbought conditions")
        
        if components.get('price_score', 0) <= -10:
            reasoning.append("Price significantly below moving average")
        elif components.get('price_score', 0) >= 10:
            reasoning.append("Price significantly above moving average")
        
        # State-specific reasoning
        if state == FearGreedState.EXTREME_FEAR:
            reasoning.append("Multiple fear indicators suggest capitulation")
        elif state == FearGreedState.EXTREME_GREED:
            reasoning.append("Multiple greed indicators suggest euphoria")
        
        return reasoning
    
    def _calculate_signal_bias(self, state: FearGreedState, confidence: float) -> str:
        """Calculate signal bias - universal logic"""
        
        bias_map = {
            FearGreedState.EXTREME_FEAR: "strongly_bullish",
            FearGreedState.FEAR: "bullish",
            FearGreedState.NEUTRAL: "neutral",
            FearGreedState.GREED: "bearish",
            FearGreedState.EXTREME_GREED: "strongly_bearish"
        }
        
        base_bias = bias_map[state]
        
        # Adjust bias strength based on confidence
        if confidence < 0.5:
            if base_bias == "strongly_bullish":
                return "bullish"
            elif base_bias == "strongly_bearish":
                return "bearish"
            elif base_bias in ["bullish", "bearish"]:
                return "neutral"
        
        return base_bias
    
    def _calculate_risk_adjustments(self, state: FearGreedState, confidence: float) -> Dict:
        """Calculate risk adjustments - universal logic with asset-specific multipliers"""
        
        # Get base adjustments for this state
        state_multipliers = {
            FearGreedState.EXTREME_FEAR: self.risk_multipliers['extreme_fear_size'],
            FearGreedState.FEAR: self.risk_multipliers['fear_size'],
            FearGreedState.NEUTRAL: 1.0,
            FearGreedState.GREED: self.risk_multipliers['greed_size'],
            FearGreedState.EXTREME_GREED: self.risk_multipliers['extreme_greed_size']
        }
        
        base_risk_adjustment = state_multipliers[state]
        
        # Calculate confidence adjustment
        confidence_adjustment = (confidence - 0.5) * 0.2  # -0.1 to +0.1
        
        # Calculate stop loss adjustment
        if state in [FearGreedState.EXTREME_FEAR, FearGreedState.FEAR]:
            stop_loss_adjustment = 1.2  # Wider stops for fear states
        elif state in [FearGreedState.EXTREME_GREED, FearGreedState.GREED]:
            stop_loss_adjustment = 0.8  # Tighter stops for greed states
        else:
            stop_loss_adjustment = 1.0
        
        # Adjust based on confidence
        if confidence > 0.7:
            base_risk_adjustment *= 1.1
        elif confidence < 0.4:
            base_risk_adjustment *= 0.9
        
        return {
            'risk_adjustment': base_risk_adjustment,
            'confidence_adjustment': confidence_adjustment,
            'stop_loss_adjustment': stop_loss_adjustment
        }
    
    def _update_state_tracking(self, new_state: FearGreedState, raw_score: float):
        """Update state tracking"""
        if new_state != self.current_state:
            self.current_state = new_state
            self.state_duration = 0
        else:
            self.state_duration += 1
        
        self.raw_score_history.append(raw_score)
        if len(self.raw_score_history) > 20:
            self.raw_score_history.pop(0)
    
    def get_state_history(self, lookback: int = 10) -> List[Dict]:
        """Get recent state history"""
        if len(self.raw_score_history) < lookback:
            lookback = len(self.raw_score_history)
        
        return [
            {
                'score': self.raw_score_history[-i-1],
                'state': self.current_state.value,
                'duration': self.state_duration
            }
            for i in range(min(lookback, len(self.raw_score_history)))
        ]
    
    def reset_state(self):
        """Reset engine state"""
        self.current_state = FearGreedState.NEUTRAL
        self.state_duration = 0
        self.raw_score_history = []

# Factory functions for easy instantiation
def create_fear_greed_engine(asset_type: str = "universal", custom_overrides: Optional[Dict] = None) -> UniversalFearGreedEngine:
    """
    Factory function to create fear/greed engine with asset-specific configuration
    
    Args:
        asset_type: 'etf', 'stock', 'crypto', or 'universal'
        custom_overrides: Optional custom parameter overrides
    
    Returns:
        UniversalFearGreedEngine: Configured engine
    """
    
    # Asset configuration mapping
    config_map = {
        'etf': ETFConfiguration(),
        'stock': StockConfiguration(),
        'crypto': CryptoConfiguration(),
        'universal': StockConfiguration(),  # Default to stock configuration
    }
    
    config = config_map.get(asset_type.lower(), StockConfiguration())
    
    return UniversalFearGreedEngine(config, custom_overrides)

# DRY utility functions for common operations
def apply_fear_greed_bias(base_signal: str, analysis: FearGreedAnalysis, 
                         asset_specific_rules: Optional[Dict] = None) -> Tuple[str, Dict]:
    """
    Apply fear/greed bias to base signal - universal function
    
    Args:
        base_signal: Original signal (BUY/SELL/HOLD)
        analysis: Fear/greed analysis
        asset_specific_rules: Optional asset-specific override rules
    
    Returns:
        Tuple[str, Dict]: (final_signal, adjustments)
    """
    
    # Default bias application rules
    bias_rules = {
        "strongly_bullish": {
            "BUY": ("BUY", {"reason": "Strong bullish bias confirmed"}),
            "HOLD": ("BUY", {"reason": "Bias overrides HOLD to BUY"}),
            "SELL": ("HOLD", {"reason": "Bias softens SELL to HOLD"})
        },
        "bullish": {
            "BUY": ("BUY", {"reason": "Bullish bias confirmed"}),
            "HOLD": ("BUY", {"reason": "Bias converts HOLD to BUY"}),
            "SELL": ("HOLD", {"reason": "Bias softens SELL to HOLD"})
        },
        "neutral": {
            "BUY": ("BUY", {"reason": "Neutral bias - keep original"}),
            "HOLD": ("HOLD", {"reason": "Neutral bias - keep original"}),
            "SELL": ("SELL", {"reason": "Neutral bias - keep original"})
        },
        "bearish": {
            "BUY": ("HOLD", {"reason": "Bearish bias softens BUY to HOLD"}),
            "HOLD": ("SELL", {"reason": "Bias converts HOLD to SELL"}),
            "SELL": ("SELL", {"reason": "Bearish bias confirmed"})
        },
        "strongly_bearish": {
            "BUY": ("SELL", {"reason": "Strong bearish bias overrides BUY"}),
            "HOLD": ("SELL", {"reason": "Bias converts HOLD to SELL"}),
            "SELL": ("SELL", {"reason": "Strong bearish bias confirmed"})
        }
    }
    
    # Apply asset-specific rules if provided
    if asset_specific_rules:
        for bias, rules in asset_specific_rules.items():
            if bias in bias_rules:
                bias_rules[bias].update(rules)
    
    # Get final signal
    bias = analysis.signal_bias
    
    # Convert base_signal to uppercase to match bias_rules keys
    base_signal_upper = base_signal.upper()
    
    # Check if the bias and signal combination exists
    if bias not in bias_rules:
        # Default to no bias if bias not found
        final_signal = base_signal
        reason = {"reason": f"Unknown bias '{bias}', keeping original signal"}
    elif base_signal_upper not in bias_rules[bias]:
        # Default to no bias if signal not found for this bias
        final_signal = base_signal
        reason = {"reason": f"Signal '{base_signal}' not found for bias '{bias}', keeping original"}
    else:
        final_signal, reason = bias_rules[bias][base_signal_upper]
    
    # Calculate adjustments
    adjustments = {
        'position_size_multiplier': analysis.risk_adjustment,
        'confidence_adjustment': analysis.confidence_adjustment,
        'stop_loss_multiplier': analysis.stop_loss_adjustment,
        'fear_greed_state': analysis.state.value,
        'fear_greed_bias': bias,
        'reason': reason['reason']
    }
    
    return final_signal, adjustments

# Example usage and testing
if __name__ == "__main__":
    # Test with different asset types
    etf_engine = create_fear_greed_engine("etf")
    stock_engine = create_fear_greed_engine("stock")
    crypto_engine = create_fear_greed_engine("crypto")
    
    # Sample market data
    market_data = MarketData(
        vix_level=25.0,
        volatility=6.5,
        rsi=45.0,
        price=150.0,
        sma20=155.0,
        asset_type="etf"
    )
    
    # Test analysis
    etf_analysis = etf_engine.calculate_fear_greed_state(market_data)
    stock_analysis = stock_engine.calculate_fear_greed_state(market_data)
    crypto_analysis = crypto_engine.calculate_fear_greed_state(market_data)
    
    print("ETF Analysis:", etf_analysis.state.value, etf_analysis.signal_bias)
    print("Stock Analysis:", stock_analysis.state.value, stock_analysis.signal_bias)
    print("Crypto Analysis:", crypto_analysis.state.value, crypto_analysis.signal_bias)
    
    # Test bias application
    final_signal, adjustments = apply_fear_greed_bias("HOLD", etf_analysis)
    print(f"Final Signal: {final_signal}, Adjustments: {adjustments}")
    
    print("Fear/Greed engine implementation complete!")
