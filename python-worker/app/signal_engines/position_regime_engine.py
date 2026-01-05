"""
Position Regime Signal Engine
Long-term trend + fundamental alignment for position trading
"""

from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from .base import (
    BaseSignalEngine, SignalResult, SignalType, SignalEngineError,
    InsufficientDataError, MarketRegime
)
from .signal_engine_utils import SignalEngineUtils
from app.observability.logging import get_logger

logger = get_logger(__name__)


class PositionRegimeEngine(BaseSignalEngine):
    """
    Position trading engine for long-term holds (30-120 days)
    
    Layer 1: Market Regime Detection
    Layer 2: Direction Model (trend persistence + fundamentals)
    Layer 3: Allocation Engine (larger positions)
    Layer 4: Reality Adjustments (drawdown limits, correlation)
    """
    
    def __init__(self):
        super().__init__()
        self.engine_name = "position_regime"
        self.engine_version = "1.0.0"
        self.min_data_length = 126  # Need at least 6 months for position analysis
    
    def generate_signal(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context
    ) -> SignalResult:
        """
        Generate position trading signal
        
        Args:
            symbol: Stock symbol
            market_data: Historical price data
            indicators: Technical indicators
            fundamentals: Fundamental data
            market_context: Market regime context
            
        Returns:
            SignalResult with position trading analysis
        """
        try:
            indicators = SignalEngineUtils.ensure_indicator_price(indicators, market_data)

            # Validate inputs
            self.validate_inputs(symbol, market_data, indicators, fundamentals, market_context)
            
            # Check minimum data length
            if len(market_data) < self.min_data_length:
                raise InsufficientDataError(
                    f"Need at least {self.min_data_length} days of data, got {len(market_data)}",
                    self.engine_name, symbol
                )
            
            # Layer 1: Market Regime Analysis
            regime_score, regime_reasoning = self._analyze_regime_for_position(market_context)
            
            # Early exit for NO_TRADE regime
            if market_context.regime == MarketRegime.NO_TRADE:
                return self._create_signal_result(
                    symbol=symbol,
                    signal=SignalType.HOLD,
                    confidence=0.1,
                    reasoning=regime_reasoning + ["Market regime: NO_TRADE - avoiding position trades"],
                    position_size_pct=0.0,
                    timeframe='position'
                )
            
            # Layer 2: Direction Model (trend + fundamentals)
            direction_score, confidence, direction_reasoning = self._calculate_direction_confidence(
                market_data, indicators, fundamentals, market_context
            )
            
            # Layer 3: Allocation Engine
            position_size, allocation_reasoning = self._determine_allocation(
                direction_score, confidence, market_context, fundamentals
            )
            
            # Layer 4: Reality Adjustments
            adjusted_position_size, reality_reasoning = self._apply_reality_adjustments(
                position_size, market_context, fundamentals
            )
            
            # Determine final signal
            signal = self._determine_signal(direction_score, confidence, market_context)
            
            # Calculate entry/exit levels
            entry_range, stop_loss, take_profit = self._calculate_position_entry_exit(
                signal, market_data, indicators, confidence
            )
            
            # Combine all reasoning
            reasoning = regime_reasoning + direction_reasoning + allocation_reasoning + reality_reasoning

            market_monitor = SignalEngineUtils.compute_market_conditions_monitor(
                market_context=market_context,
                market_data=market_data,
                indicators=indicators,
            )
            
            return self._create_signal_result(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                reasoning=reasoning,
                position_size_pct=adjusted_position_size,
                entry_price_range=entry_range,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe='position',
                metadata={
                    'regime_score': regime_score,
                    'direction_score': direction_score,
                    'trend_persistence_score': direction_reasoning[0] if direction_reasoning else 0,
                    'fundamental_boost': fundamentals.get('fundamental_boost', 0),
                    'hold_duration_days': self._estimate_hold_duration(market_context, confidence),
                    'market_conditions_monitor': market_monitor.to_dict(),
                }
            )
            
        except Exception as e:
            if isinstance(e, SignalEngineError):
                raise
            raise SignalEngineError(f"Failed to generate position regime signal: {str(e)}", 
                                 self.engine_name, symbol)
    
    def _analyze_regime_for_position(self, market_context) -> Tuple[float, List[str]]:
        """Analyze market regime specifically for position trading"""
        reasoning = []
        score = 0.0
        
        # Regime scoring for position trading
        if market_context.regime == MarketRegime.BULL:
            score = 1.0
            reasoning.append("Market regime: BULL (optimal for position longs)")
        elif market_context.regime == MarketRegime.BEAR:
            score = -0.3
            reasoning.append("Market regime: BEAR (caution for position trades)")
        elif market_context.regime == MarketRegime.HIGH_VOL_CHOP:
            score = -0.1
            reasoning.append("Market regime: HIGH_VOL_CHOP (selective position trades)")
        else:  # NO_TRADE
            score = -1.0
            reasoning.append("Market regime: NO_TRADE (avoid position trading)")
        
        # VIX consideration for position trading
        if market_context.vix < 12:
            score += 0.1
            reasoning.append(f"Very low VIX ({market_context.vix:.1f}) - stable for positions")
        elif market_context.vix > 35:
            score -= 0.2
            reasoning.append(f"High VIX ({market_context.vix:.1f}) - risk for positions")
        
        # NASDAQ trend strength
        if market_context.nasdaq_trend == "bullish":
            score += 0.2
            reasoning.append("NASDAQ trend bullish - supports position trades")
        elif market_context.nasdaq_trend == "bearish":
            score -= 0.2
            reasoning.append("NASDAQ trend bearish - headwind for positions")
        
        return score, reasoning
    
    def _calculate_direction_confidence(
        self, market_data: pd.DataFrame, indicators: Dict[str, Any], 
        fundamentals: Dict[str, Any], market_context
    ) -> Tuple[float, float, List[str]]:
        """
        Calculate direction probability using position-specific features
        """
        reasoning = []
        score = 0.0
        
        # Feature 1: Trend persistence (21d, 63d, 126d)
        trend_score, trend_reasoning = self._analyze_trend_persistence(market_data)
        score += trend_score * 0.4
        reasoning.extend(trend_reasoning)
        
        # Feature 2: Fundamental alignment
        fund_score, fund_reasoning = self._analyze_fundamental_alignment(fundamentals)
        score += fund_score * 0.3
        reasoning.extend(fund_reasoning)
        
        # Feature 3: Sector rotation
        sector_score, sector_reasoning = self._analyze_sector_rotation(fundamentals, market_context)
        score += sector_score * 0.2
        reasoning.extend(sector_reasoning)
        
        # Feature 4: Long-term technical health
        tech_score, tech_reasoning = self._analyze_long_term_technicals(indicators, market_data)
        score += tech_score * 0.1
        reasoning.extend(tech_reasoning)
        
        # Convert score to confidence
        confidence = max(0.0, min(1.0, 0.5 + score))
        
        return score, confidence, reasoning
    
    def _analyze_trend_persistence(self, market_data: pd.DataFrame) -> Tuple[float, List[str]]:
        """Analyze long-term trend persistence"""
        reasoning = []
        score = 0.0
        
        if len(market_data) < 126:
            return 0.0, ["Insufficient data for trend analysis"]
        
        closes = market_data['close'].astype(float).values
        
        # Calculate returns for different periods
        returns_21d = (closes[-1] - closes[-22]) / closes[-22] if len(closes) > 21 else 0
        returns_63d = (closes[-1] - closes[-64]) / closes[-64] if len(closes) > 63 else 0
        returns_126d = (closes[-1] - closes[-127]) / closes[-127] if len(closes) > 126 else 0
        
        # Score 21-day trend
        if returns_21d > 0.05:  # > 5%
            score += 0.2
            reasoning.append(f"Strong 21-day trend: +{returns_21d*100:.1f}%")
        elif returns_21d < -0.05:  # < -5%
            score -= 0.2
            reasoning.append(f"Weak 21-day trend: {returns_21d*100:.1f}%")
        
        # Score 63-day trend (quarterly)
        if returns_63d > 0.15:  # > 15%
            score += 0.3
            reasoning.append(f"Strong quarterly trend: +{returns_63d*100:.1f}%")
        elif returns_63d < -0.15:  # < -15%
            score -= 0.3
            reasoning.append(f"Weak quarterly trend: {returns_63d*100:.1f}%")
        
        # Score 126-day trend (6 months)
        if returns_126d > 0.25:  # > 25%
            score += 0.2
            reasoning.append(f"Strong 6-month trend: +{returns_126d*100:.1f}%")
        elif returns_126d < -0.25:  # < -25%
            score -= 0.2
            reasoning.append(f"Weak 6-month trend: {returns_126d*100:.1f}%")
        
        # Trend consistency (how often above SMA50)
        if len(market_data) >= 60:
            recent_data = market_data.tail(60)
            sma50 = recent_data['close'].rolling(50).mean()
            above_sma50_pct = (recent_data['close'] > sma50).sum() / len(recent_data)
            
            if above_sma50_pct > 0.8:  # Above SMA50 > 80% of time
                score += 0.2
                reasoning.append(f"Trend persistence: {above_sma50_pct*100:.0f}% above SMA50")
            elif above_sma50_pct < 0.2:  # Below SMA50 > 80% of time
                score -= 0.2
                reasoning.append(f"Weak trend: {above_sma50_pct*100:.0f}% above SMA50")
        
        return score, reasoning
    
    def _analyze_fundamental_alignment(self, fundamentals: Dict[str, Any]) -> Tuple[float, List[str]]:
        """Analyze fundamental quality for position trading"""
        reasoning = []
        score = 0.0
        
        # Earnings consistency
        earnings_surprises = fundamentals.get('earnings_surprise_last_4q', [])
        if earnings_surprises:
            positive_surprises = sum(1 for s in earnings_surprises if s > 0)
            if positive_surprises >= 3:  # 3+ positive surprises
                score += 0.2
                reasoning.append(f"Strong earnings: {positive_surprises}/4 positive surprises")
            elif positive_surprises <= 1:  # 0-1 positive surprises
                score -= 0.1
                reasoning.append(f"Weak earnings: {positive_surprises}/4 positive surprises")
        
        # Revenue growth sustainability
        revenue_growth = fundamentals.get('revenue_growth', 0)
        if revenue_growth > 0.20:  # > 20% growth
            score += 0.2
            reasoning.append(f"Strong revenue growth: {revenue_growth*100:.1f}%")
        elif revenue_growth < 0.05:  # < 5% growth
            score -= 0.1
            reasoning.append(f"Weak revenue growth: {revenue_growth*100:.1f}%")
        
        # Margin expansion
        margin_trend = fundamentals.get('operating_margin_trend', 0)
        if margin_trend > 0.02:  # Expanding > 2%
            score += 0.2
            reasoning.append("Operating margin expanding (+QoQ)")
        elif margin_trend < -0.02:  # Contracting > 2%
            score -= 0.1
            reasoning.append("Operating margin contracting (-QoQ)")
        
        # Market cap (larger caps more stable for positions)
        market_cap = fundamentals.get('market_cap', 0)
        if market_cap > 10e9:  # > $10B
            score += 0.1
            reasoning.append(f"Large cap stability: ${market_cap/1e9:.0f}B")
        elif market_cap < 1e9:  # < $1B
            score -= 0.1
            reasoning.append(f"Small cap risk: ${market_cap/1e9:.1f}B")
        
        return score, reasoning
    
    def _analyze_sector_rotation(self, fundamentals: Dict[str, Any], market_context) -> Tuple[float, List[str]]:
        """Analyze sector rotation and momentum"""
        reasoning = []
        score = 0.0
        
        sector = fundamentals.get('sector', 'unknown')
        sector_rotation = market_context.sector_rotation or {}
        
        # Get sector momentum score
        sector_momentum = sector_rotation.get(sector.lower(), 0)
        
        if sector_momentum > 0.1:  # Strong sector momentum
            score += 0.2
            reasoning.append(f"Sector momentum strong: {sector.title()}")
        elif sector_momentum < -0.1:  # Weak sector momentum
            score -= 0.1
            reasoning.append(f"Sector momentum weak: {sector.title()}")
        
        # Sector-regime alignment
        if market_context.regime == MarketRegime.BULL:
            growth_sectors = ['technology', 'consumer discretionary', 'communication services']
            if sector.lower() in growth_sectors:
                score += 0.1
                reasoning.append(f"Growth sector in bull market: {sector.title()}")
        elif market_context.regime == MarketRegime.BEAR:
            defensive_sectors = ['utilities', 'consumer staples', 'healthcare']
            if sector.lower() in defensive_sectors:
                score += 0.1
                reasoning.append(f"Defensive sector in bear market: {sector.title()}")
        
        return score, reasoning
    
    def _analyze_long_term_technicals(self, indicators: Dict[str, Any], market_data: pd.DataFrame) -> Tuple[float, List[str]]:
        """Analyze long-term technical health"""
        reasoning = []
        score = 0.0
        
        if not indicators:
            return 0.0, ["No technical indicators available"]
        
        # Long-term moving averages
        sma50 = indicators.get('sma50')
        sma200 = indicators.get('sma200')
        
        if sma50 and sma200:
            if sma50 > sma200:
                score += 0.2
                reasoning.append("Golden cross (SMA50 > SMA200)")
            else:
                score -= 0.2
                reasoning.append("Death cross (SMA50 < SMA200)")
        
        # Long-term RSI (avoid extreme overbought/oversold for positions)
        rsi = indicators.get('rsi')
        if rsi:
            if 40 <= rsi <= 60:
                score += 0.1
                reasoning.append(f"RSI balanced for position: {rsi:.1f}")
            elif rsi > 80:
                score -= 0.1
                reasoning.append(f"RSI extended overbought: {rsi:.1f}")
        
        # Volume confirmation
        if len(market_data) >= 20:
            recent_volume = market_data.tail(20)['volume'].mean()
            historical_volume = market_data['volume'].mean()
            
            if recent_volume > historical_volume * 1.2:
                score += 0.1
                reasoning.append("Volume confirmation (above average)")
        
        return score, reasoning
    
    def _determine_allocation(
        self, direction_score: float, confidence: float, market_context, fundamentals: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Determine position size for position trading"""
        reasoning = []
        
        # Base position size for position trading (larger than swing)
        base_size = 0.15  # 15% base position
        
        # Scale by confidence
        confidence_multiplier = confidence / 0.60  # Normalize to 60% threshold
        
        # Fundamental boost for quality companies
        fundamental_boost = 1.0
        margin = fundamentals.get('operating_margin', 0)
        growth = fundamentals.get('revenue_growth', 0)
        
        if margin > 0.25 and growth > 0.20:  # High margin + strong growth
            fundamental_boost = 1.2
            reasoning.append("Quality boost: High margin + strong growth")
        elif margin < 0.10 or growth < 0.05:  # Low margin or weak growth
            fundamental_boost = 0.8
            reasoning.append("Quality discount: Low margin or weak growth")
        
        # Regime-based exposure limits
        if market_context.regime == MarketRegime.BULL:
            max_exposure = 0.20  # Max 20% in bull
            regime_multiplier = 1.2
        elif market_context.regime == MarketRegime.BEAR:
            max_exposure = 0.10  # Max 10% in bear
            regime_multiplier = 0.6
        else:  # HIGH_VOL_CHOP
            max_exposure = 0.12  # Max 12% in choppy
            regime_multiplier = 0.8
        
        # Calculate position size
        position_size = base_size * confidence_multiplier * fundamental_boost * regime_multiplier
        position_size = max(0, min(max_exposure, position_size))
        
        reasoning.append(f"Position size: {position_size*100:.1f}% (confidence + quality scaled)")
        
        if market_context.regime == MarketRegime.BEAR:
            reasoning.append("Reduced exposure in bear market")
        
        return position_size, reasoning
    
    def _apply_reality_adjustments(
        self, position_size: float, market_context, fundamentals: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """Apply position trading reality adjustments"""
        reasoning = []
        adjusted_size = position_size
        
        # Drawdown limits
        if market_context.regime == MarketRegime.HIGH_VOL_CHOP:
            adjusted_size = position_size * 0.6
            reasoning.append("Position size reduced (volatility risk)")
        
        # Correlation check (simplified)
        sector = fundamentals.get('sector', 'unknown')
        if market_context.sector_rotation and sector.lower() in market_context.sector_rotation:
            sector_correlation = abs(market_context.sector_rotation[sector.lower()])
            if sector_correlation > 0.3:  # High sector correlation
                adjusted_size *= 0.8
                reasoning.append("Size reduced (high sector correlation)")
        
        # Market cap adjustment (small caps get smaller positions)
        market_cap = fundamentals.get('market_cap', 0)
        if market_cap < 2e9:  # < $2B
            adjusted_size *= 0.7
            reasoning.append("Size reduced (small cap risk)")
        
        return adjusted_size, reasoning
    
    def _determine_signal(self, direction_score: float, confidence: float, market_context) -> SignalType:
        """Determine final signal for position trading"""
        
        # Lower confidence threshold for position trading (longer timeframe)
        if confidence > 0.60 and direction_score > 0.0:
            return SignalType.BUY
        elif confidence > 0.60 and direction_score < -0.1:
            return SignalType.SELL
        else:
            return SignalType.HOLD
    
    def _calculate_position_entry_exit(
        self, signal: SignalType, market_data: pd.DataFrame, indicators: Dict[str, Any], confidence: float
    ) -> Tuple:
        """Calculate entry, stop loss, and take profit for position trading"""
        
        if len(market_data) == 0 or signal == SignalType.HOLD:
            return None, None, []
        
        current_price = market_data.iloc[-1]['close']
        
        # Wider entry range for position trading
        entry_width = 0.02 if confidence > 0.7 else 0.03  # 2-3%
        entry_range = (current_price * (1 - entry_width), current_price * (1 + entry_width))
        
        # Wider stop loss for position trading
        stop_distance = 0.12 if confidence > 0.7 else 0.18  # 12-18%
        if signal == SignalType.BUY:
            stop_loss = current_price * (1 - stop_distance)
        else:  # SELL
            stop_loss = current_price * (1 + stop_distance)
        
        # Multiple take profit targets
        if signal == SignalType.BUY:
            take_profit = [
                current_price * (1 + stop_distance * 1.5),  # First target: 1.5x risk
                current_price * (1 + stop_distance * 2.5)   # Second target: 2.5x risk
            ]
        else:  # SELL
            take_profit = [
                current_price * (1 - stop_distance * 1.5),  # First target
                current_price * (1 - stop_distance * 2.5)   # Second target
            ]
        
        return entry_range, stop_loss, take_profit
    
    def _estimate_hold_duration(self, market_context, confidence: float) -> int:
        """Estimate hold duration in days"""
        base_duration = 60  # 2 months base
        
        if confidence > 0.7:
            base_duration = 90  # 3 months for high confidence
        
        if market_context.regime == MarketRegime.BULL:
            base_duration = int(base_duration * 1.2)  # Longer holds in bull
        elif market_context.regime == MarketRegime.BEAR:
            base_duration = int(base_duration * 0.7)  # Shorter holds in bear
        
        return min(max(base_duration, 30), 120)  # Between 1-4 months
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine metadata"""
        return {
            'name': self.engine_name,
            'display_name': 'Position Regime Engine',
            'description': 'Long-term trend + fundamental alignment for position trading (30-120 days)',
            'tier': 'ELITE',
            'timeframe': 'position',
            'version': self.engine_version,
            'features': [
                'Trend persistence analysis',
                'Fundamental quality scoring',
                'Sector rotation awareness',
                'Risk-adjusted position sizing',
                'Drawdown and correlation adjustments'
            ]
        }
    
    def get_required_indicators(self) -> list:
        """Return required indicators"""
        return ['price', 'volume', 'rsi', 'sma50', 'sma200', 'ema20']
    
    def get_required_fundamentals(self) -> list:
        """Return required fundamentals"""
        return [
            'sector', 'market_cap', 'operating_margin', 'revenue_growth',
            'earnings_surprise_last_4q', 'operating_margin_trend'
        ]
