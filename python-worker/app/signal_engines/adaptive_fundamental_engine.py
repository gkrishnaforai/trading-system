"""
Adaptive Fundamental Signal Engine
Sector-aware, margin-sensitive, regime-conscious scoring
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np

from .base import (
    BaseSignalEngine, SignalResult, SignalType, SignalEngineError,
    InsufficientDataError, MarketRegime
)
from app.observability.logging import get_logger

logger = get_logger(__name__)


class SectorConfig:
    """Sector baseline configuration for fundamental analysis"""
    
    SECTORS = {
        'technology-software': {
            'margin_min': 0.15, 'margin_median': 0.22, 'margin_excellent': 0.30,
            'pe_low': 20, 'pe_median': 35, 'pe_high': 60,
            'growth_min': 0.15, 'growth_strong': 0.40,
            'margin_weight': 0.3, 'growth_weight': 0.4, 'valuation_weight': 0.3
        },
        'technology-semiconductors': {
            'margin_min': 0.20, 'margin_median': 0.28, 'margin_excellent': 0.35,
            'pe_low': 15, 'pe_median': 22, 'pe_high': 30,
            'growth_min': 0.10, 'growth_strong': 0.30,
            'margin_weight': 0.4, 'growth_weight': 0.3, 'valuation_weight': 0.3
        },
        'finance': {
            'margin_min': 0.25, 'margin_median': 0.35, 'margin_excellent': 0.45,
            'pe_low': 8, 'pe_median': 12, 'pe_high': 18,
            'growth_min': 0.05, 'growth_strong': 0.15,
            'margin_weight': 0.5, 'growth_weight': 0.2, 'valuation_weight': 0.3
        },
        'retail': {
            'margin_min': 0.03, 'margin_median': 0.07, 'margin_excellent': 0.12,
            'pe_low': 10, 'pe_median': 16, 'pe_high': 25,
            'growth_min': 0.05, 'growth_strong': 0.20,
            'margin_weight': 0.3, 'growth_weight': 0.4, 'valuation_weight': 0.3
        },
        'healthcare': {
            'margin_min': 0.10, 'margin_median': 0.18, 'margin_excellent': 0.28,
            'pe_low': 15, 'pe_median': 25, 'pe_high': 40,
            'growth_min': 0.08, 'growth_strong': 0.25,
            'margin_weight': 0.3, 'growth_weight': 0.4, 'valuation_weight': 0.3
        },
        'energy': {
            'margin_min': 0.05, 'margin_median': 0.12, 'margin_excellent': 0.20,
            'pe_low': 8, 'pe_median': 15, 'pe_high': 25,
            'growth_min': 0.00, 'growth_strong': 0.15,
            'margin_weight': 0.4, 'growth_weight': 0.2, 'valuation_weight': 0.4
        }
    }
    
    @classmethod
    def get_config(cls, sector: str) -> Dict[str, Any]:
        """Get sector configuration, defaulting to technology-software"""
        sector_key = sector.lower().replace(' ', '-')
        return cls.SECTORS.get(sector_key, cls.SECTORS['technology-software'])


class AdaptiveFundamentalEngine(BaseSignalEngine):
    """
    Sector-aware, margin-sensitive, regime-conscious signal engine
    
    Decision Flow:
    1. Detect market regime
    2. Load sector baseline rules
    3. Score margins (relative + trend)
    4. Score revenue growth
    5. Technical timing overlay
    6. Aggregate → Signal + Confidence
    """
    
    def __init__(self):
        super().__init__()
        self.engine_name = "adaptive_fundamental"
        self.engine_version = "1.0.0"
    
    def generate_signal(
        self,
        symbol: str,
        market_data: pd.DataFrame,
        indicators: Dict[str, Any],
        fundamentals: Dict[str, Any],
        market_context
    ) -> SignalResult:
        """
        Generate adaptive fundamental signal
        
        Args:
            symbol: Stock symbol
            market_data: Historical price data
            indicators: Technical indicators
            fundamentals: Fundamental data
            market_context: Market regime context
            
        Returns:
            SignalResult with adaptive fundamental analysis
        """
        try:
            # Validate inputs
            self.validate_inputs(symbol, market_data, indicators, fundamentals, market_context)
            
            # Step 1: Market regime check
            if market_context.regime == MarketRegime.NO_TRADE:
                return self._create_signal_result(
                    symbol=symbol,
                    signal=SignalType.HOLD,
                    confidence=0.1,
                    reasoning=["Market regime: NO_TRADE - avoiding all positions"],
                    position_size_pct=0.0,
                    timeframe='position'
                )
            
            # Step 2: Load sector configuration
            sector = fundamentals.get('sector', 'technology')
            sector_config = SectorConfig.get_config(sector)
            
            # Step 3: Score margins
            margin_score, margin_reasoning = self._score_margins(fundamentals, sector_config)
            
            # Step 4: Score revenue growth
            growth_score, growth_reasoning = self._score_growth(fundamentals, sector_config)
            
            # Step 5: Technical timing
            technical_score, technical_reasoning = self._score_technical_timing(indicators, market_data)
            
            # Step 6: Aggregate scores with regime weights
            final_score, confidence = self._aggregate_scores(
                margin_score, growth_score, technical_score, market_context, sector_config
            )
            
            # Step 7: Determine signal
            signal = self._determine_signal(final_score, confidence)
            
            # Step 8: Calculate position size
            position_size = self._calculate_position_size(signal, confidence, market_context)
            
            # Step 9: Generate entry/exit levels
            entry_range, stop_loss, take_profit = self._calculate_entry_exit(
                signal, market_data, indicators, confidence
            )
            
            # Combine all reasoning
            reasoning = [
                f"Sector: {sector.title()} ({sector_config['growth_strong']*100:.0f}%+ growth tolerance)",
                f"Market regime: {market_context.regime.value}"
            ] + margin_reasoning + growth_reasoning + technical_reasoning
            
            return self._create_signal_result(
                symbol=symbol,
                signal=signal,
                confidence=confidence,
                reasoning=reasoning,
                position_size_pct=position_size,
                entry_price_range=entry_range,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe='position',
                metadata={
                    'sector': sector,
                    'margin_score': margin_score,
                    'growth_score': growth_score,
                    'technical_score': technical_score,
                    'final_score': final_score,
                    'regime': market_context.regime.value
                }
            )
            
        except Exception as e:
            if isinstance(e, SignalEngineError):
                raise
            raise SignalEngineError(f"Failed to generate adaptive fundamental signal: {str(e)}", 
                                 self.engine_name, symbol)
    
    def _score_margins(self, fundamentals: Dict[str, Any], sector_config: Dict[str, Any]) -> tuple:
        """Score operating margins relative to sector"""
        reasoning = []
        score = 0.0
        
        # Get operating margin
        margin = fundamentals.get('operating_margin')
        if margin is None:
            margin = fundamentals.get('profit_margin')
        
        if margin is None:
            return 0.0, ["No margin data available"]
        
        # Compare to sector benchmarks
        sector_median = sector_config['margin_median']
        sector_excellent = sector_config['margin_excellent']
        
        if margin > sector_excellent:
            score += 0.3
            reasoning.append(f"Operating margin: {margin*100:.1f}% (excellent for sector)")
        elif margin > sector_median:
            score += 0.2
            reasoning.append(f"Operating margin: {margin*100:.1f}% (above sector median)")
        elif margin > sector_config['margin_min']:
            score += 0.0
            reasoning.append(f"Operating margin: {margin*100:.1f}% (acceptable for sector)")
        else:
            score -= 0.2
            reasoning.append(f"Operating margin: {margin*100:.1f}% (below sector minimum)")
        
        # Check margin trend
        margin_trend = fundamentals.get('operating_margin_trend')
        if margin_trend:
            if margin_trend > 0.02:  # Expanding > 2%
                score += 0.2
                reasoning.append("Margin trend: Expanding (+QoQ)")
            elif margin_trend < -0.02:  # Contracting > 2%
                score -= 0.1
                reasoning.append("Margin trend: Contracting (-QoQ)")
        
        return score, reasoning
    
    def _score_growth(self, fundamentals: Dict[str, Any], sector_config: Dict[str, Any]) -> tuple:
        """Score revenue growth relative to sector"""
        reasoning = []
        score = 0.0
        
        # Get revenue growth
        growth = fundamentals.get('revenue_growth')
        if growth is None:
            return 0.0, ["No revenue growth data available"]
        
        # Compare to sector benchmarks
        sector_strong = sector_config['growth_strong']
        sector_min = sector_config['growth_min']
        
        if growth > sector_strong:
            score += 0.3
            reasoning.append(f"Revenue growth: {growth*100:.1f}% (strong for sector)")
        elif growth > sector_min:
            score += 0.1
            reasoning.append(f"Revenue growth: {growth*100:.1f}% (adequate for sector)")
        else:
            score -= 0.1
            reasoning.append(f"Revenue growth: {growth*100:.1f}% (below sector expectations)")
        
        # Check growth acceleration
        growth_acceleration = fundamentals.get('revenue_growth_acceleration')
        if growth_acceleration:
            score += 0.1
            reasoning.append("Growth accelerating (faster than last quarter)")
        
        return score, reasoning
    
    def _score_technical_timing(self, indicators: Dict[str, Any], market_data: pd.DataFrame) -> tuple:
        """Score technical timing for entry"""
        reasoning = []
        score = 0.0
        
        if not indicators:
            return 0.0, ["No technical indicators available"]
        
        # RSI timing
        rsi = indicators.get('rsi')
        if rsi:
            if 30 <= rsi <= 70:
                score += 0.1
                reasoning.append(f"RSI healthy ({rsi:.1f})")
            elif rsi > 80:
                score -= 0.1
                reasoning.append(f"RSI overbought ({rsi:.1f})")
            elif rsi < 20:
                score += 0.1
                reasoning.append(f"RSI oversold ({rsi:.1f})")
        
        # Trend alignment
        ema20 = indicators.get('ema20')
        sma50 = indicators.get('sma50')
        sma200 = indicators.get('sma200')
        
        if ema20 and sma50 and sma200:
            if ema20 > sma50 > sma200:
                score += 0.2
                reasoning.append("Strong uptrend (EMA20 > SMA50 > SMA200)")
            elif ema20 > sma50:
                score += 0.1
                reasoning.append("Bullish trend (EMA20 > SMA50)")
            elif ema20 < sma50 < sma200:
                score -= 0.1
                reasoning.append("Bearish trend (EMA20 < SMA50 < SMA200)")
        
        # MACD confirmation
        macd = indicators.get('macd')
        macd_signal = indicators.get('macd_signal')
        if macd and macd_signal:
            if macd > macd_signal:
                score += 0.1
                reasoning.append("MACD bullish (above signal)")
            else:
                score -= 0.1
                reasoning.append("MACD bearish (below signal)")
        
        return score, reasoning
    
    def _aggregate_scores(
        self,
        margin_score: float,
        growth_score: float,
        technical_score: float,
        market_context,
        sector_config: Dict[str, Any]
    ) -> tuple:
        """Aggregate component scores with regime weights"""
        
        # Adjust weights based on regime
        if market_context.regime == MarketRegime.BULL:
            # Favor growth in bull markets
            weights = {
                'margin': sector_config['margin_weight'] * 0.8,
                'growth': sector_config['growth_weight'] * 1.2,
                'technical': sector_config['valuation_weight']
            }
        elif market_context.regime == MarketRegime.BEAR:
            # Favor margins/valuation in bear markets
            weights = {
                'margin': sector_config['margin_weight'] * 1.2,
                'growth': sector_config['growth_weight'] * 0.8,
                'technical': sector_config['valuation_weight']
            }
        else:  # HIGH_VOL_CHOP
            # Balanced approach in choppy markets
            weights = {
                'margin': sector_config['margin_weight'],
                'growth': sector_config['growth_weight'],
                'technical': sector_config['valuation_weight']
            }
        
        # Normalize weights
        total_weight = sum(weights.values())
        weights = {k: v/total_weight for k, v in weights.items()}
        
        # Calculate weighted score
        final_score = (
            margin_score * weights['margin'] +
            growth_score * weights['growth'] +
            technical_score * weights['technical']
        )
        
        # Convert to confidence (0-1)
        confidence = max(0.0, min(1.0, 0.5 + final_score))
        
        return final_score, confidence
    
    def _determine_signal(self, final_score: float, confidence: float) -> SignalType:
        """Determine signal from aggregated score"""
        
        if confidence > 0.7 and final_score > 0.2:
            return SignalType.BUY
        elif confidence < 0.4 or final_score < -0.2:
            return SignalType.SELL
        else:
            return SignalType.HOLD
    
    def _calculate_position_size(self, signal: SignalType, confidence: float, market_context) -> float:
        """Calculate position size based on signal and regime"""
        
        if signal == SignalType.HOLD:
            return 0.0
        
        # Base position size
        base_size = 0.12  # 12% base position
        
        # Scale by confidence
        confidence_multiplier = confidence / 0.7  # Normalize to 70% threshold
        
        # Regime adjustment
        if market_context.regime == MarketRegime.BULL:
            regime_multiplier = 1.2
        elif market_context.regime == MarketRegime.BEAR:
            regime_multiplier = 0.5
        else:  # HIGH_VOL_CHOP
            regime_multiplier = 0.7
        
        # Calculate final size
        position_size = base_size * confidence_multiplier * regime_multiplier
        
        # Cap at reasonable limits
        if signal == SignalType.BUY:
            position_size = min(0.20, position_size)  # Max 20% long
        else:  # SELL
            position_size = -min(0.20, position_size)  # Max 20% short
        
        return position_size
    
    def _calculate_entry_exit(
        self, signal: SignalType, market_data: pd.DataFrame, indicators: Dict[str, Any], confidence: float
    ) -> tuple:
        """Calculate entry, stop loss, and take profit levels"""
        
        if len(market_data) == 0:
            return None, None, []
        
        current_price = market_data.iloc[-1]['close']
        
        if signal == SignalType.HOLD:
            return None, None, []
        
        # Entry range (±1% for high confidence, ±2% for lower confidence)
        entry_width = 0.01 if confidence > 0.7 else 0.02
        entry_range = (current_price * (1 - entry_width), current_price * (1 + entry_width))
        
        # Stop loss (5% for high confidence, 8% for lower confidence)
        stop_distance = 0.05 if confidence > 0.7 else 0.08
        if signal == SignalType.BUY:
            stop_loss = current_price * (1 - stop_distance)
        else:  # SELL
            stop_loss = current_price * (1 + stop_distance)
        
        # Take profit (10% for high confidence, 15% for lower confidence)
        profit_distance = 0.10 if confidence > 0.7 else 0.15
        if signal == SignalType.BUY:
            take_profit = [current_price * (1 + profit_distance)]
        else:  # SELL
            take_profit = [current_price * (1 - profit_distance)]
        
        return entry_range, stop_loss, take_profit
    
    def get_engine_metadata(self) -> Dict[str, Any]:
        """Return engine metadata"""
        return {
            'name': self.engine_name,
            'display_name': 'Adaptive Fundamental Engine',
            'description': 'Sector-aware, margin-sensitive, regime-conscious fundamental analysis',
            'tier': 'PRO',
            'timeframe': 'position',
            'version': self.engine_version,
            'features': [
                'Sector-relative margin scoring',
                'Revenue growth analysis',
                'Market regime weight adjustments',
                'Technical timing overlay',
                'Structural superiority detection'
            ]
        }
    
    def get_required_indicators(self) -> list:
        """Return required indicators"""
        return ['price', 'volume', 'rsi', 'macd', 'sma50', 'sma200', 'ema20']
    
    def get_required_fundamentals(self) -> list:
        """Return required fundamentals"""
        return [
            'sector', 'market_cap', 'operating_margin', 'profit_margin',
            'revenue_growth', 'operating_margin_trend', 'revenue_growth_acceleration'
        ]
