#!/usr/bin/env python3
"""
Professional Indicator States - Eliminates Contradictions
Core Idea: Separate Indicator State from Signal Decision
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Tuple


class MACDState(str, Enum):
    """MACD momentum states - no contradictions possible"""
    BEARISH = "bearish"
    RECOVERING = "recovering"
    BULLISH = "bullish"
    EXHAUSTED = "exhausted"


class RSIState(str, Enum):
    """RSI states - no contradictions possible"""
    OVERSOLD = "oversold"
    NEUTRAL = "neutral"
    OVERBOUGHT = "overbought"


class TrendState(str, Enum):
    """Trend states based on price vs MAs - no contradictions possible"""
    STRONG_BULL = "strong_bull"
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"


class VolatilityState(str, Enum):
    """Volatility regimes - no contradictions possible"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class LiquidityState(str, Enum):
    """Liquidity states - no contradictions possible"""
    THIN = "thin"
    NORMAL = "normal"
    STRONG = "strong"


class FearGreedState(str, Enum):
    """Behavioral states - no contradictions possible"""
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"


class TradeAction(str, Enum):
    """Final trading actions - no contradictions possible"""
    BUY = "buy"
    ADD = "add"
    HOLD = "hold"
    SELL = "sell"
    REDUCE = "reduce"


@dataclass
class IndicatorStates:
    """Container for all indicator states - single source of truth"""
    trend: TrendState
    macd: MACDState
    rsi: RSIState
    volatility: VolatilityState
    liquidity: LiquidityState
    fear_greed: FearGreedState
    
    # Additional context
    volume_ratio: float
    price: float
    confidence: float = 0.0


class IndicatorClassifier:
    """Professional indicator state classifier - eliminates contradictions"""
    
    @staticmethod
    def classify_macd(macd: float, signal: float, histogram: float) -> MACDState:
        """
        Classify MACD into non-contradictory states
        This eliminates "MACD bearish + bullish crossover" contradictions
        """
        if macd < 0 and macd < signal and histogram < 0:
            return MACDState.BEARISH
        elif macd < 0 and macd > signal and histogram > 0:
            return MACDState.RECOVERING  # Bullish crossover but still negative
        elif macd > 0 and macd > signal and histogram > 0:
            return MACDState.BULLISH
        elif macd > 0 and histogram < 0:
            return MACDState.EXHAUSTED
        else:
            # Default to bearish for safety
            return MACDState.BEARISH
    
    @staticmethod
    def classify_rsi(rsi: float) -> RSIState:
        """Classify RSI into non-contradictory states"""
        if rsi < 30:
            return RSIState.OVERSOLD
        elif rsi > 70:
            return RSIState.OVERBOUGHT
        else:
            return RSIState.NEUTRAL
    
    @staticmethod
    def classify_trend(price: float, ema20: float, sma50: float, macd: float) -> TrendState:
        """
        Classify trend into non-contradictory states
        Uses both price position and MACD for confirmation
        """
        if price > ema20 > sma50 and macd > 0:
            return TrendState.STRONG_BULL
        elif price > ema20:
            return TrendState.BULL
        elif price < ema20 < sma50 and macd < 0:
            return TrendState.BEAR
        else:
            return TrendState.NEUTRAL
    
    @staticmethod
    def classify_volatility(volatility: float) -> VolatilityState:
        """Classify volatility into non-contradictory states"""
        if volatility > 8.0:
            return VolatilityState.EXTREME
        elif volatility > 6.0:
            return VolatilityState.HIGH
        elif volatility > 3.0:
            return VolatilityState.NORMAL
        else:
            return VolatilityState.LOW
    
    @staticmethod
    def classify_liquidity(volume: float, avg_volume: float) -> Tuple[LiquidityState, float]:
        """Classify liquidity into non-contradictory states"""
        volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0
        
        if volume_ratio > 1.5:
            return LiquidityState.STRONG, volume_ratio
        elif volume_ratio > 0.8:
            return LiquidityState.NORMAL, volume_ratio
        else:
            return LiquidityState.THIN, volume_ratio
    
    @staticmethod
    def classify_fear_greed(vix: float, market_sentiment: float = 0.5) -> FearGreedState:
        """Classify fear/greed into non-contradictory states"""
        if vix < 15 and market_sentiment > 0.7:
            return FearGreedState.GREED
        elif vix > 25 or market_sentiment < 0.3:
            return FearGreedState.FEAR
        else:
            return FearGreedState.NEUTRAL


class SignalDecisionEngine:
    """
    Professional signal decision engine - uses states, not raw indicators
    This makes contradictions mathematically impossible
    """
    
    @staticmethod
    def decide_action(states: IndicatorStates) -> TradeAction:
        """
        Make trading decision based on states only
        This eliminates all contradictions
        """
        trend, macd, rsi, vol, liq, fg = states.trend, states.macd, states.rsi, states.volatility, states.liquidity, states.fear_greed
        
        # 🚀 STRONG BUY (early entry or continuation)
        if trend in {TrendState.BULL, TrendState.STRONG_BULL}:
            if macd in {MACDState.RECOVERING, MACDState.BULLISH}:
                if rsi != RSIState.OVERBOUGHT:
                    if liq in {LiquidityState.NORMAL, LiquidityState.STRONG}:
                        if vol in {VolatilityState.LOW, VolatilityState.NORMAL}:
                            return TradeAction.BUY
        
        # ➕ ADD (trend continuation, not early)
        if trend == TrendState.STRONG_BULL:
            if macd == MACDState.BULLISH:
                if rsi == RSIState.NEUTRAL:
                    if liq == LiquidityState.STRONG:
                        if vol == VolatilityState.NORMAL:
                            return TradeAction.ADD
        
        # ⚠️ HOLD (trend intact but stretched)
        if trend in {TrendState.BULL, TrendState.STRONG_BULL}:
            if rsi == RSIState.OVERBOUGHT or macd == MACDState.EXHAUSTED:
                return TradeAction.HOLD
        
        # 🔴 SELL (trend + momentum broken)
        if trend == TrendState.BEAR:
            if macd in {MACDState.BEARISH, MACDState.EXHAUSTED}:
                if liq in {LiquidityState.NORMAL, LiquidityState.STRONG}:
                    return TradeAction.SELL
        
        # 🟠 REDUCE (risk management)
        if trend in {TrendState.BULL, TrendState.STRONG_BULL}:
            if vol == VolatilityState.HIGH:
                if rsi == RSIState.OVERBOUGHT:
                    return TradeAction.REDUCE
        
        # Default to HOLD
        return TradeAction.HOLD


class SignalTextGenerator:
    """
    Professional signal text generator - uses states only
    This makes contradictions mathematically impossible
    """
    
    # State-to-text mappings - enhanced narrative style
    TREND_TEXT = {
        TrendState.STRONG_BULL: "🟢 Strong uptrend (price above key moving averages)",
        TrendState.BULL: "🟢 Uptrend intact (price above major averages)",
        TrendState.NEUTRAL: "🟡 Sideways consolidation (price around key levels)",
        TrendState.BEAR: "🔴 Downtrend (price below key moving averages)"
    }
    
    MACD_TEXT = {
        MACDState.BEARISH: "🔴 MACD bearish (negative momentum, avoid long positions)",
        MACDState.RECOVERING: "🟡 MACD recovering (bullish crossover forming, momentum improving)",
        MACDState.BULLISH: "🟢 MACD bullish (momentum expanding, supports trend)",
        MACDState.EXHAUSTED: "🟠 MACD losing momentum (caution on new entries)"
    }
    
    RSI_TEXT = {
        RSIState.OVERSOLD: "🟢 RSI oversold (mean-reversion buying opportunity)",
        RSIState.NEUTRAL: "🟡 RSI neutral (healthy momentum, room for upside)",
        RSIState.OVERBOUGHT: "🔴 RSI overbought (profit-taking zone, risk of pullback)"
    }
    
    VOLATILITY_TEXT = {
        VolatilityState.LOW: "🟡 Low volatility (complacency, watch for breakouts)",
        VolatilityState.NORMAL: "🟢 Normal volatility (optimal trading conditions)",
        VolatilityState.HIGH: "🟠 High volatility (unstable, reduce position size)",
        VolatilityState.EXTREME: "🔴 Extreme volatility (risk-off environment)"
    }
    
    LIQUIDITY_TEXT = {
        LiquidityState.THIN: "🔴 Thin liquidity (avoid noise, high slippage risk)",
        LiquidityState.NORMAL: "🟡 Normal liquidity (adequate for position sizing)",
        LiquidityState.STRONG: "🟢 Strong liquidity (institutional-friendly, high conviction)"
    }
    
    FEAR_GREED_TEXT = {
        FearGreedState.FEAR: "🟢 Fear environment (contrarian buying opportunities)",
        FearGreedState.NEUTRAL: "🟡 Balanced fear/greed (neutral market sentiment)",
        FearGreedState.GREED: "🔴 Greed environment (risk reduction, profit-taking)"
    }
    
    @classmethod
    def generate_signal_text(cls, states: IndicatorStates) -> list[str]:
        """
        Generate signal text from states only
        This makes contradictions mathematically impossible
        """
        lines = []
        
        # Enhanced narrative-style explanations
        lines.append(cls.TREND_TEXT[states.trend])
        lines.append(cls.MACD_TEXT[states.macd])
        lines.append(cls.RSI_TEXT[states.rsi])
        lines.append(cls.VOLATILITY_TEXT[states.volatility])
        lines.append(cls.LIQUIDITY_TEXT[states.liquidity])
        lines.append(cls.FEAR_GREED_TEXT[states.fear_greed])
        
        # Add context with better formatting
        lines.append(f"📊 Volume: {states.volume_ratio:.1f}x average")
        lines.append(f"💰 Price: ${states.price:.2f}")
        
        # Add market phase classification
        market_phase = cls._classify_market_phase(states)
        lines.append(f"🎯 Market Phase: {market_phase}")
        
        return lines
    
    @classmethod
    def generate_action_reasoning(cls, action: TradeAction, states: IndicatorStates) -> list[str]:
        """Generate action-specific reasoning for educational value"""
        reasons = []
        
        if action == TradeAction.BUY:
            reasons.append("🚀 Early entry opportunity identified")
            if states.trend in {TrendState.BULL, TrendState.STRONG_BULL}:
                reasons.append("✅ Trend supports new positions")
            if states.macd == MACDState.RECOVERING:
                reasons.append("🟡 Momentum beginning to turn positive")
            if states.rsi == RSIState.OVERSOLD:
                reasons.append("🟢 Oversold conditions provide mean-reversion opportunity")
            if states.liquidity == LiquidityState.STRONG:
                reasons.append("✅ Strong liquidity supports position entry")
                
        elif action == TradeAction.ADD:
            reasons.append("📈 Trend continuation opportunity")
            if states.trend == TrendState.STRONG_BULL:
                reasons.append("✅ Strong uptrend supports position addition")
            if states.macd == MACDState.BULLISH:
                reasons.append("🟢 Momentum confirmed and expanding")
            if states.rsi == RSIState.NEUTRAL:
                reasons.append("🟡 RSI neutral - room for further upside")
            if states.liquidity == LiquidityState.STRONG:
                reasons.append("✅ Strong liquidity supports institutional sizing")
                
        elif action == TradeAction.HOLD:
            reasons.append("⏸️ Hold current positions")
            if states.rsi == RSIState.OVERBOUGHT:
                reasons.append("⚠️ Overbought conditions - wait for pullback")
            if states.macd == MACDState.EXHAUSTED:
                reasons.append("⚠️ Momentum exhaustion - reduce risk")
            if states.volatility == VolatilityState.HIGH:
                reasons.append("⚠️ High volatility - maintain current positions")
                
        elif action == TradeAction.SELL:
            reasons.append("📉 Exit long positions")
            if states.trend == TrendState.BEAR:
                reasons.append("🔴 Downtrend confirmed - exit positions")
            if states.macd in {MACDState.BEARISH, MACDState.EXHAUSTED}:
                reasons.append("🔴 Momentum broken - risk management")
            if states.liquidity in {LiquidityState.NORMAL, LiquidityState.STRONG}:
                reasons.append("✅ Adequate liquidity for orderly exit")
                
        elif action == TradeAction.REDUCE:
            reasons.append("📉 Reduce position size")
            if states.volatility == VolatilityState.HIGH:
                reasons.append("⚠️ High volatility - reduce exposure")
            if states.rsi == RSIState.OVERBOUGHT:
                reasons.append("⚠️ Overbought - take partial profits")
            if states.trend in {TrendState.BULL, TrendState.STRONG_BULL}:
                reasons.append("🟡 Trend still intact but risk elevated")
        
        return reasons
    
    @classmethod
    def _classify_market_phase(cls, states: IndicatorStates) -> str:
        """Classify the current market phase for better context"""
        if states.trend == TrendState.STRONG_BULL:
            if states.macd in {MACDState.RECOVERING, MACDState.BULLISH}:
                if states.rsi == RSIState.NEUTRAL:
                    return "EARLY/MID TREND CONTINUATION"
                elif states.rsi == RSIState.OVERSOLD:
                    return "DIP BUYING OPPORTUNITY"
            elif states.macd == MACDState.EXHAUSTED:
                return "LATE STAGE - CAUTION ADVISED"
        elif states.trend == TrendState.BEAR:
            if states.macd in {MACDState.RECOVERING, MACDState.BULLISH}:
                return "POTENTIAL REVERSAL ZONE"
            else:
                return "DOWNTREND INTACT"
        else:
            return "CONSOLIDATION PHASE"
        
        return "TRANSITIONAL PHASE"


def classify_all_indicators(
    price: float, ema20: float, sma50: float,
    macd: float, macd_signal: float, macd_histogram: float,
    rsi: float, volatility: float, volume: float, avg_volume: float,
    vix: float = 20.0, market_sentiment: float = 0.5
) -> IndicatorStates:
    """
    Classify all indicators into states - eliminates contradictions
    """
    classifier = IndicatorClassifier()
    
    # Classify each indicator into its state
    trend_state = classifier.classify_trend(price, ema20, sma50, macd)
    macd_state = classifier.classify_macd(macd, macd_signal, macd_histogram)
    rsi_state = classifier.classify_rsi(rsi)
    volatility_state = classifier.classify_volatility(volatility)
    liquidity_state, volume_ratio = classifier.classify_liquidity(volume, avg_volume)
    fear_greed_state = classifier.classify_fear_greed(vix, market_sentiment)
    
    return IndicatorStates(
        trend=trend_state,
        macd=macd_state,
        rsi=rsi_state,
        volatility=volatility_state,
        liquidity=liquidity_state,
        fear_greed=fear_greed_state,
        volume_ratio=volume_ratio,
        price=price
    )


def generate_professional_signal(
    price: float, ema20: float, sma50: float,
    macd: float, macd_signal: float, macd_histogram: float,
    rsi: float, volatility: float, volume: float, avg_volume: float,
    vix: float = 20.0, market_sentiment: float = 0.5
) -> Tuple[TradeAction, IndicatorStates, list[str]]:
    """
    Generate professional signal using state-based architecture
    This makes contradictions mathematically impossible
    """
    # Step 1: Classify all indicators into states
    states = classify_all_indicators(
        price, ema20, sma50, macd, macd_signal, macd_histogram,
        rsi, volatility, volume, avg_volume, vix, market_sentiment
    )
    
    # Step 2: Make decision based on states only
    action = SignalDecisionEngine.decide_action(states)
    
    # Step 3: Generate text from states only
    reasoning = SignalTextGenerator.generate_signal_text(states)
    
    return action, states, reasoning
