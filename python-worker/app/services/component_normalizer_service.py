"""
Component Normalizer Service
Centralizes all component normalization to ensure mathematical consistency
All components normalized to [-1, +1] range for clean mathematical operations
"""

import numpy as np
from typing import Dict, Any, Optional, List
from app.observability.logging import get_logger

logger = get_logger(__name__)


class ComponentNormalizer:
    """Centralized component normalization with consistent [-1, +1] range"""

    @staticmethod
    def normalize_rsi_trend(rsi_history: Optional[List[float]]) -> float:
        """Normalize RSI trend to [-1, +1].

        Intended to capture "RSI rising off 40" (bullish) and weakening RSI near 60-70 (bearish).
        Uses last ~5 points if available.
        """
        if not rsi_history or len(rsi_history) < 3:
            return 0.0

        # Use last values in chronological order (assume caller passes chronological; if not, still works roughly)
        recent = [v for v in rsi_history[-5:] if v is not None]
        if len(recent) < 3:
            return 0.0

        rsi_now = float(recent[-1])
        rsi_prev = float(recent[0])
        slope = (rsi_now - rsi_prev) / max(1, (len(recent) - 1))

        # Base trend from slope (tanh bounds). Typical RSI daily moves are small; scale by 2.
        slope_score = float(np.tanh(slope / 2.0))

        # Context boosts: "rising off 40" is a swing-entry rule.
        off_40_boost = 0.0
        if 35 <= rsi_now <= 60 and rsi_now >= 40 and slope > 0:
            off_40_boost = 0.5

        # Weakening near overbought (captures early rollover, not divergence).
        overbought_roll = 0.0
        if rsi_now >= 60 and slope < 0:
            overbought_roll = -0.5

        return float(np.clip(0.6 * slope_score + 0.4 * (off_40_boost + overbought_roll), -1.0, 1.0))

    @staticmethod
    def normalize_volume_confirmation(
        volume: Optional[float],
        avg_volume_20d: Optional[float],
        price: Optional[float] = None,
        ema_20: Optional[float] = None,
    ) -> float:
        """Normalize volume confirmation to [-1, +1].

        Positive when volume is meaningfully above average (conviction).
        Negative when volume is meaningfully below average (low participation).
        If price and ema_20 are provided, amplify positive score when price is above EMA20
        and amplify negative score when price is below EMA20.
        """
        if volume is None or avg_volume_20d is None or avg_volume_20d <= 0:
            return 0.0

        vol_ratio = float(volume) / float(avg_volume_20d)
        # Center around 1.0; treat 1.5x as strong and 0.6x as weak.
        raw = np.tanh((vol_ratio - 1.0) / 0.4)  # ~[-1, +1]

        if price is not None and ema_20 is not None:
            if price > ema_20:
                raw = raw * 1.15
            elif price < ema_20:
                raw = raw * 1.15

        return float(np.clip(raw, -1.0, 1.0))

    @staticmethod
    def normalize_volume_trend(volume_history: Optional[List[float]]) -> float:
        """Normalize volume trend (increasing/decreasing participation) to [-1, +1].

        Uses recent average vs prior average.
        Example: last 3 bars vs previous 7 bars (from a 10-bar history).
        """
        if not volume_history or len(volume_history) < 6:
            return 0.0

        clean = [float(v) for v in volume_history if v is not None and v > 0]
        if len(clean) < 6:
            return 0.0

        # Split: recent 3 vs prior window
        recent = clean[-3:]
        prior = clean[:-3]
        if not prior:
            return 0.0

        recent_avg = float(np.mean(recent))
        prior_avg = float(np.mean(prior))
        if prior_avg <= 0:
            return 0.0

        ratio = recent_avg / prior_avg
        # Map ratio around 1.0 to [-1, +1]. 1.25 -> strongly positive; 0.8 -> strongly negative.
        return float(np.clip(np.tanh((ratio - 1.0) / 0.15), -1.0, 1.0))

    @staticmethod
    def apply_breakout_confirmation(
        breakout_score: float,
        current_price: Optional[float],
        ema_20: Optional[float],
        volume_confirmation: float,
        volume_trend: float,
    ) -> float:
        """Gate/shape breakout score using price>EMA20 + volume confirmation + volume trend.

        Goal: classify breakout as "real" only when participation is expanding.
        - If conditions are not met, dampen breakout magnitude.
        - If met, slightly boost breakout magnitude.
        """
        if breakout_score == 0.0:
            return 0.0

        above_ema = (current_price is not None and ema_20 is not None and current_price > ema_20)
        vol_ok = volume_confirmation > 0.25
        trend_ok = volume_trend > 0.15

        if above_ema and vol_ok and trend_ok:
            return float(np.clip(breakout_score * 1.15, -1.0, 1.0))

        # If attempting upside breakout but no confirmation -> dampen
        if breakout_score > 0:
            return float(breakout_score * 0.35)

        # For downside moves, keep as-is (sell breakouts can happen on declining volume too)
        return float(breakout_score)
    
    @staticmethod
    def normalize_relative_strength(relative_strength: float) -> float:
        """
        Normalize relative strength to [-1, +1]
        ±20% = ±1.0 scale using tanh for smooth bounding
        """
        if relative_strength is None:
            return 0.0
        return np.tanh(relative_strength / 0.2)
    
    @staticmethod
    def normalize_trend_alignment(price: float, sma_20: float, sma_50: float, sma_200: Optional[float] = None) -> float:
        """
        Normalize trend alignment to [-1, +1]
        Strong uptrend: +1.0, Strong downtrend: -1.0, Neutral: 0.0
        """
        if price is None or sma_20 is None or sma_50 is None:
            return 0.0
        
        # Strong uptrend
        if price > sma_20 > sma_50:
            if sma_200 and price > sma_200:
                return 1.0  # Strong uptrend
            return 0.7  # Medium uptrend
        
        # Strong downtrend  
        elif price < sma_20 < sma_50:
            if sma_200 and price < sma_200:
                return -1.0  # Strong downtrend
            return -0.7  # Medium downtrend
        
        # Neutral/sideways
        else:
            return 0.0
    
    @staticmethod
    def normalize_momentum(
        rsi: float,
        macd: Optional[float] = None,
        macd_signal: Optional[float] = None,
        rsi_history: Optional[List[float]] = None,
    ) -> float:
        """
        Normalize momentum indicators to [-1, +1]
        Combines RSI and MACD for comprehensive momentum view
        """
        momentum_score = 0.0
        
        # RSI contribution (±0.4 max)
        if rsi is not None:
            if rsi < 30:  # Oversold
                momentum_score += 0.4 * (1 - rsi / 30)  # 0 to 0.4
            elif rsi > 70:  # Overbought
                momentum_score -= 0.4 * ((rsi - 70) / 30)  # 0 to -0.4
        
        # MACD contribution (±0.6 max)
        if macd is not None and macd_signal is not None:
            macd_diff = macd - macd_signal
            # Normalize MACD difference using tanh for smooth bounding
            macd_contribution = 0.6 * np.tanh(macd_diff / 0.1)  # Scale factor for MACD
            momentum_score += macd_contribution

        # RSI trend contribution (±0.2 max)
        rsi_trend = ComponentNormalizer.normalize_rsi_trend(rsi_history)
        momentum_score += 0.2 * rsi_trend
        
        return np.clip(momentum_score, -1.0, 1.0)
    
    @staticmethod
    def normalize_breakout_potential(
        current_price: float, 
        recent_high: float, 
        recent_low: float, 
        atr: float
    ) -> float:
        """
        Normalize breakout potential to [-1, +1]
        Uses ATR-normalized distance from range
        """
        if current_price is None or recent_high is None or recent_low is None or atr is None or atr == 0:
            return 0.0
        
        range_mid = (recent_high + recent_low) / 2
        range_size = recent_high - recent_low
        
        if range_size == 0:
            return 0.0
        
        # Position within range (-1 to +1)
        range_position = (current_price - range_mid) / (range_size / 2)
        
        # ATR scaling for volatility adjustment
        atr_adjustment = min(atr / (range_size * 0.1), 2.0)  # Cap adjustment
        
        # Combine range position with ATR scaling
        breakout_score = np.tanh(range_position * atr_adjustment)
        
        return np.clip(breakout_score, -1.0, 1.0)
    
    @staticmethod
    def normalize_volatility(atr_percentile: float) -> float:
        """
        Normalize volatility to [-1, +1]
        Ideal volatility (40-70th percentile) = 0.0
        Extreme low/high volatility = ±1.0
        """
        if atr_percentile is None:
            return 0.0
        
        # Ideal range: 40-70th percentile
        if 40 <= atr_percentile <= 70:
            return 0.0  # Ideal volatility
        elif atr_percentile < 40:
            # Low volatility: scale to -1.0 at 0th percentile
            return -(40 - atr_percentile) / 40
        else:
            # High volatility: scale to +1.0 at 100th percentile  
            return (atr_percentile - 70) / 30
    
    @staticmethod
    def normalize_all_components(market_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Normalize all market data components to [-1, +1] range
        Returns dictionary of normalized components
        """
        normalized = {}
        
        try:
            # Relative Strength
            if 'relative_strength' in market_data:
                normalized['rs'] = ComponentNormalizer.normalize_relative_strength(
                    market_data['relative_strength']
                )
            
            # Trend Alignment
            if all(key in market_data for key in ['current_price', 'sma_20', 'sma_50']):
                normalized['trend'] = ComponentNormalizer.normalize_trend_alignment(
                    market_data['current_price'],
                    market_data['sma_20'], 
                    market_data['sma_50'],
                    market_data.get('sma_200')
                )
            
            # Momentum
            if 'rsi' in market_data:
                normalized['momentum'] = ComponentNormalizer.normalize_momentum(
                    market_data['rsi'],
                    market_data.get('macd'),
                    market_data.get('macd_signal'),
                    market_data.get('rsi_history')
                )

                # Expose RSI trend as its own component for transparency/debugging
                normalized['rsi_trend'] = ComponentNormalizer.normalize_rsi_trend(
                    market_data.get('rsi_history')
                )

            # Volume Confirmation
            if 'volume' in market_data and 'avg_volume_20d' in market_data:
                normalized['volume_confirmation'] = ComponentNormalizer.normalize_volume_confirmation(
                    market_data.get('volume'),
                    market_data.get('avg_volume_20d'),
                    market_data.get('current_price'),
                    market_data.get('ema_20'),
                )

            # Volume trend (increasing/decreasing)
            if 'volume_history' in market_data:
                normalized['volume_trend'] = ComponentNormalizer.normalize_volume_trend(
                    market_data.get('volume_history')
                )
            
            # Breakout Potential
            if all(key in market_data for key in ['current_price', 'recent_high', 'recent_low', 'atr']):
                breakout_raw = ComponentNormalizer.normalize_breakout_potential(
                    market_data['current_price'],
                    market_data['recent_high'],
                    market_data['recent_low'], 
                    market_data['atr']
                )

                normalized['breakout_raw'] = breakout_raw

                normalized['breakout'] = ComponentNormalizer.apply_breakout_confirmation(
                    breakout_raw,
                    market_data.get('current_price'),
                    market_data.get('ema_20'),
                    normalized.get('volume_confirmation', 0.0),
                    normalized.get('volume_trend', 0.0),
                )
            
            # Volatility
            if 'volatility_percentile' in market_data:
                normalized['volatility'] = ComponentNormalizer.normalize_volatility(
                    market_data['volatility_percentile']
                )
            
            logger.debug(f"Normalized components: {normalized}")
            
        except Exception as e:
            logger.error(f"Error normalizing components: {e}")
            # Return empty dict on error to prevent system failure
            return {}
        
        return normalized
