"""
Common Signal Engine Utilities
Shared logic extracted from TQQQ engine for reuse in generic ETF engines
"""

from typing import List, Tuple, Dict, Any
from app.signal_engines.signal_calculator_core import SignalType, MarketConditions, SignalResult

class SignalEngineUtils:
    """Common utilities for signal engines"""
    
    @staticmethod
    def calculate_trend_conditions(conditions: MarketConditions) -> Tuple[bool, bool]:
        """
        Calculate uptrend and downtrend conditions
        Reused from TQQQ engine logic
        """
        is_uptrend = (
            conditions.sma_20 > conditions.sma_50 and
            conditions.current_price > conditions.sma_50
        )
        
        is_downtrend = (
            conditions.sma_20 < conditions.sma_50 and
            conditions.current_price < conditions.sma_50
        )
        
        return is_uptrend, is_downtrend
    
    @staticmethod
    def get_rsi_status(rsi: float, oversold: float = 35, overbought: float = 70) -> str:
        """Get RSI status description"""
        if rsi < oversold:
            return "OVERSOLD"
        elif rsi > overbought:
            return "OVERBOUGHT"
        else:
            return "NEUTRAL"
    
    @staticmethod
    def get_trend_status(sma20: float, sma50: float) -> str:
        """Get trend status description"""
        if sma20 > sma50:
            return "UPTREND"
        elif sma20 < sma50:
            return "DOWNTREND"
        else:
            return "SIDEWAYS"
    
    @staticmethod
    def get_price_vs_sma_status(price: float, sma: float) -> str:
        """Get price vs SMA status"""
        return "ABOVE" if price > sma else "BELOW"
    
    @staticmethod
    def create_signal_result(signal: SignalType, confidence: float, reasoning: List[str], 
                           metadata: Dict[str, Any] = None) -> SignalResult:
        """Create signal result with standard metadata"""
        if metadata is None:
            metadata = {}
        
        return SignalResult(
            signal=signal,
            confidence=confidence,
            reasoning=reasoning,
            metadata=metadata
        )

class MeanReversionLogic:
    """Mean reversion signal logic extracted from TQQQ engine"""
    
    @staticmethod
    def generate_signal(conditions: MarketConditions, config: Dict[str, Any]) -> SignalResult:
        """
        Generate mean reversion signal with ETF-specific configuration
        Based on TQQQ engine logic but configurable
        """
        # Extract ETF-specific thresholds
        rsi_oversold = config.get('rsi_oversold', 45.0)
        rsi_moderately_oversold = config.get('rsi_moderately_oversold', 35.0)
        rsi_overbought = config.get('rsi_overbought', 65.0)
        mean_reversion_rsi_upper = config.get('mean_reversion_rsi_upper', 60.0)
        mean_reversion_momentum_threshold = config.get('mean_reversion_momentum_threshold', 0.04)
        
        # Conditions
        is_oversold = conditions.rsi < rsi_oversold
        is_moderately_oversold = conditions.rsi < rsi_moderately_oversold
        is_recently_down = conditions.recent_change < -0.02
        
        # SELL conditions (from TQQQ engine)
        is_overbought = conditions.rsi > rsi_overbought
        is_recently_up = conditions.recent_change > 0.015
        
        reasoning = []
        
        # SELL: Overbought with recent strength (from TQQQ)
        if is_overbought and is_recently_up:
            reasoning.extend([
                "Mean reversion: Overbought with recent strength",
                f"RSI overbought: {conditions.rsi:.1f}",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Mean reversion sell expected",
                "Take profits now"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.6, reasoning, {'strategy': 'mean_reversion_overbought'}
            )
        
        # SELL: Overbought even without recent strength (from TQQQ)
        if is_overbought:
            reasoning.extend([
                "Mean reversion: Overbought conditions",
                f"RSI overbought: {conditions.rsi:.1f}",
                "Price likely to revert",
                "Sell into strength",
                "Risk management"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.5, reasoning, {'strategy': 'mean_reversion_overbought_basic'}
            )
        
        # SELL: Recent strength in neutral RSI (from TQQQ)
        if mean_reversion_rsi_upper < conditions.rsi < mean_reversion_rsi_upper + 10 and conditions.recent_change > mean_reversion_momentum_threshold:
            reasoning.extend([
                "Mean reversion: Recent strength in neutral zone",
                f"RSI neutral: {conditions.rsi:.1f}",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Likely mean reversion",
                "Sell into momentum"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.4, reasoning, {'strategy': 'mean_reversion_neutral_strength'}
            )
        
        # BUY conditions (from TQQQ)
        if is_oversold and is_recently_down:
            reasoning.extend([
                "Strong oversold with recent decline",
                f"RSI oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Mean reversion bounce expected"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.BUY, 0.7, reasoning, {'strategy': 'mean_reversion_oversold'}
            )
        
        # BUY: Moderately oversold (from TQQQ)
        if is_moderately_oversold and is_recently_down:
            reasoning.extend([
                "Moderate oversold with decline",
                f"RSI moderately oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Potential bounce opportunity"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.BUY, 0.6, reasoning, {'strategy': 'mean_reversion_moderate'}
            )
        
        # HOLD: No clear setup
        reasoning.extend([
            "Mean reversion: No clear setup",
            f"RSI: {conditions.rsi:.1f}",
            f"Recent change: {conditions.recent_change:.2%}",
            "Waiting for clarity"
        ])
        return SignalEngineUtils.create_signal_result(
            SignalType.HOLD, 0.0, reasoning, {'strategy': 'mean_reversion_wait'}
        )

class TrendContinuationLogic:
    """Trend continuation signal logic extracted from TQQQ engine"""
    
    @staticmethod
    def generate_signal(conditions: MarketConditions, config: Dict[str, Any]) -> SignalResult:
        """
        Generate trend continuation signal with ETF-specific configuration
        Based on TQQQ engine logic but configurable
        """
        reasoning = []
        
        # BUY: Pullback to support (from TQQQ)
        if conditions.current_price <= conditions.sma_20 and conditions.current_price > conditions.sma_50:
            reasoning.extend([
                "Trend continuation: Healthy pullback",
                f"Price pulled back to SMA20: ${conditions.sma_20:.2f}",
                f"RSI in pullback zone: {conditions.rsi:.1f}",
                "Above SMA50 support: ${conditions.sma_50:.2f}",
                "Trend resumption expected"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.BUY, 0.65, reasoning, {'strategy': 'trend_pullback'}
            )
        
        # BUY: Additional pullback (from TQQQ)
        if conditions.current_price <= conditions.sma_50 and conditions.rsi < 45:
            reasoning.extend([
                "Trend continuation: Deep pullback",
                f"Price pulled back to SMA50: ${conditions.sma_50:.2f}",
                f"RSI oversold: {conditions.rsi:.1f}",
                "Strong support level",
                "Potential trend resumption"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.BUY, 0.6, reasoning, {'strategy': 'trend_deep_pullback'}
            )
        
        # SELL: Overextended in uptrend (from TQQQ)
        if conditions.rsi > 70 and conditions.recent_change > 0.03:
            reasoning.extend([
                "Trend continuation: Overextended",
                f"RSI overbought: {conditions.rsi:.1f}",
                f"Recent rise: {conditions.recent_change:.2%}",
                "Take profits on strength"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.5, reasoning, {'strategy': 'trend_overextended'}
            )
        
        # HOLD: No clear setup
        reasoning.extend([
            "Trend continuation: No clear setup",
            f"RSI: {conditions.rsi:.1f}",
            f"Price vs SMA20: ${conditions.current_price:.2f} vs ${conditions.sma_20:.2f}",
            "Waiting for pullback"
        ])
        return SignalEngineUtils.create_signal_result(
            SignalType.HOLD, 0.0, reasoning, {'strategy': 'trend_wait'}
        )

class BreakoutLogic:
    """Breakout signal logic extracted from TQQQ engine"""
    
    @staticmethod
    def generate_signal(conditions: MarketConditions, config: Dict[str, Any]) -> SignalResult:
        """
        Generate breakout signal with ETF-specific configuration
        Based on TQQQ engine logic but configurable
        """
        breakout_momentum_threshold = config.get('breakout_momentum_threshold', 0.02)
        breakout_rsi_upper_bound = config.get('breakout_rsi_upper_bound', 70.0)
        
        reasoning = []
        
        # BUY: Momentum breakout (from TQQQ)
        if conditions.recent_change > breakout_momentum_threshold and conditions.rsi < breakout_rsi_upper_bound:
            reasoning.extend([
                "Breakout: Momentum detected",
                f"Recent change: {conditions.recent_change:.2%}",
                f"RSI momentum: {conditions.rsi:.1f}",
                "Breakout continuation expected"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.BUY, 0.6, reasoning, {'strategy': 'breakout_momentum'}
            )
        
        # BUY: Strong momentum (from TQQQ)
        if conditions.recent_change > 0.03 and conditions.rsi > 60:
            reasoning.extend([
                "Breakout: Strong momentum",
                f"Strong momentum: {conditions.recent_change:.2%}",
                f"RSI strength: {conditions.rsi:.1f}",
                "Momentum continuation"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.BUY, 0.7, reasoning, {'strategy': 'breakout_strong'}
            )
        
        # SELL: Failed breakout (from TQQQ)
        if conditions.rsi < 57 and conditions.recent_change < 0:
            reasoning.extend([
                "Breakout: Failed breakout",
                f"RSI weakened: {conditions.rsi:.1f}",
                f"Recent change: {conditions.recent_change:.2%}",
                "Exit failed breakout"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.5, reasoning, {'strategy': 'breakout_failed'}
            )
        
        # HOLD: No clear setup
        reasoning.extend([
            "Breakout: No clear setup",
            f"RSI: {conditions.rsi:.1f}",
            "Waiting for momentum"
        ])
        return SignalEngineUtils.create_signal_result(
            SignalType.HOLD, 0.0, reasoning, {'strategy': 'breakout_wait'}
        )

class VolatilityExpansionLogic:
    """Volatility expansion signal logic extracted from TQQQ engine"""
    
    @staticmethod
    def generate_signal(conditions: MarketConditions, config: Dict[str, Any]) -> SignalResult:
        """
        Generate volatility expansion signal with ETF-specific configuration
        Based on TQQQ engine logic but configurable
        """
        high_volatility_threshold = config.get('high_volatility_threshold', 8.0)
        rsi_extreme_oversold = config.get('rsi_extreme_oversold', 30.0)
        
        reasoning = []
        
        # SELL: Sharp decline (from TQQQ)
        if conditions.recent_change < -0.02:
            reasoning.extend([
                "Volatility expansion: Sharp decline detected",
                f"Recent decline: {conditions.recent_change:.2%}",
                f"High volatility: {conditions.volatility:.1f}%",
                "Risk-off: Exit positions immediately",
                "Capital preservation mode"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.8, reasoning, {'strategy': 'volatility_decline'}
            )
        
        # SELL: High volatility with any negative change (from TQQQ)
        if conditions.recent_change < 0 and conditions.volatility > 5.0:
            reasoning.extend([
                "Volatility expansion: Risk-off with decline",
                f"Negative change: {conditions.recent_change:.2%}",
                f"High volatility: {conditions.volatility:.1f}%",
                "Market stress detected",
                "Reduce exposure"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.7, reasoning, {'strategy': 'volatility_stress'}
            )
        
        # SELL: Very high volatility regardless of direction (from TQQQ)
        if conditions.volatility > high_volatility_threshold:
            reasoning.extend([
                "Volatility expansion: Extreme volatility",
                f"Very high volatility: {conditions.volatility:.1f}%",
                "Market uncertainty high",
                "Risk-off: Stay in cash",
                "Wait for stability"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.6, reasoning, {'strategy': 'volatility_extreme'}
            )
        
        # SELL: RSI overbought in volatile market (from TQQQ)
        if conditions.rsi > 65:
            reasoning.extend([
                "Volatility expansion: Overbought in volatile market",
                f"RSI overbought: {conditions.rsi:.1f}",
                f"Volatility elevated: {conditions.volatility:.1f}%",
                "Take profits on strength",
                "Reduce position size"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.SELL, 0.6, reasoning, {'strategy': 'volatility_overbought'}
            )
        
        # BUY: Strong oversold in volatile market (from TQQQ)
        if conditions.rsi < rsi_extreme_oversold and conditions.recent_change > -0.05:
            reasoning.extend([
                "Volatility expansion: Deep oversold bounce",
                f"Extreme oversold: {conditions.rsi:.1f}",
                f"Recent decline: {conditions.recent_change:.2%}",
                "Potential bounce opportunity",
                "Small position only"
            ])
            return SignalEngineUtils.create_signal_result(
                SignalType.BUY, 0.5, reasoning, {'strategy': 'volatility_oversold'}
            )
        
        # HOLD: No clear setup
        reasoning.extend([
            "Volatility expansion: No clear setup",
            f"Volatility: {conditions.volatility:.1f}%",
            f"Recent change: {conditions.recent_change:.2%}",
            "Wait for clarity",
            "Risk management priority"
        ])
        return SignalEngineUtils.create_signal_result(
            SignalType.HOLD, 0.0, reasoning, {'strategy': 'volatility_wait'}
        )
