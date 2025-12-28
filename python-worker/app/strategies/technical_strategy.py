"""
Technical Analysis Strategy
Implements the standard technical analysis strategy with EMA crossovers, MACD, RSI
"""
import logging
from typing import Dict, Any, Optional
import pandas as pd

from app.strategies.base import BaseStrategy, StrategyResult

logger = logging.getLogger(__name__)


class TechnicalStrategy(BaseStrategy):
    """
    Technical analysis strategy using EMA crossovers, MACD, RSI
    
    Buy Signal:
    - Price > SMA200 (long-term bullish)
    - EMA20 > SMA50 (medium-term bullish)
    - EMA20 crosses above EMA50
    - MACD > Signal (positive momentum)
    - RSI < 70 (not overbought)
    
    Sell Signal:
    - EMA20 crosses below EMA50 OR trend weakening
    - MACD < Signal OR RSI < 50 (momentum fading)
    """
    
    def get_name(self) -> str:
        return "technical"
    
    def get_description(self) -> str:
        return "Technical analysis strategy using EMA crossovers, MACD, RSI, and trend confirmation"
    
    def get_required_indicators(self) -> list:
        """
        Return list of required indicator names with minimum data points
        
        Returns:
            List of required indicator names
        """
        return [
            'price',
            'ema20',  # Needs 20 periods
            'ema50',  # Needs 50 periods
            'sma200',  # Needs 200 periods
            'macd_line',  # Needs 26 periods
            'macd_signal',  # Needs 26 periods
            'rsi',  # Needs 14 periods
        ]
    
    def generate_signal(
        self,
        indicators: Dict[str, Any],
        market_data: Optional[pd.DataFrame] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> StrategyResult:
        """
        Generate signal based on technical indicators
        """
        # Extract indicators
        price = indicators.get('price')
        ema20 = indicators.get('ema20')
        ema50 = indicators.get('ema50')
        sma200 = indicators.get('sma200')
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        rsi = indicators.get('rsi')
        volume = indicators.get('volume')
        volume_ma = indicators.get('volume_ma')
        long_term_trend = indicators.get('long_term_trend')
        medium_term_trend = indicators.get('medium_term_trend')
        
        # Validate required indicators - check if they exist (not None) and are not empty
        required_indicators = [price, ema20, ema50, sma200, macd_line, macd_signal, rsi]
        if not all(
            ind is not None and 
            (not isinstance(ind, pd.Series) or len(ind) > 0) and
            (not isinstance(ind, (int, float)) or not pd.isna(ind))
            for ind in required_indicators
        ):
            return StrategyResult(
                signal='hold',
                confidence=0.0,
                reason="Missing required indicators",
                metadata={},
                strategy_name=self.name
            )
        
        # Get latest values (assuming indicators are Series, get last value)
        if isinstance(price, pd.Series):
            price_val = price.iloc[-1] if len(price) > 0 else None
            ema20_val = ema20.iloc[-1] if len(ema20) > 0 else None
            ema50_val = ema50.iloc[-1] if len(ema50) > 0 else None
            sma200_val = sma200.iloc[-1] if len(sma200) > 0 else None
            macd_line_val = macd_line.iloc[-1] if len(macd_line) > 0 else None
            macd_signal_val = macd_signal.iloc[-1] if len(macd_signal) > 0 else None
            rsi_val = rsi.iloc[-1] if len(rsi) > 0 else None
        else:
            price_val = price
            ema20_val = ema20
            ema50_val = ema50
            sma200_val = sma200
            macd_line_val = macd_line
            macd_signal_val = macd_signal
            rsi_val = rsi
        
        # Check for NaN values
        if any(pd.isna(val) for val in [price_val, ema20_val, ema50_val, sma200_val, 
                                        macd_line_val, macd_signal_val, rsi_val]):
            return StrategyResult(
                signal='hold',
                confidence=0.0,
                reason="Insufficient data for indicators",
                metadata={},
                strategy_name=self.name
            )
        
        # Detect trends
        is_bullish_long_term = long_term_trend == 'bullish' if isinstance(long_term_trend, str) else (
            long_term_trend.iloc[-1] == 'bullish' if isinstance(long_term_trend, pd.Series) else False
        )
        is_bullish_medium_term = medium_term_trend == 'bullish' if isinstance(medium_term_trend, str) else (
            medium_term_trend.iloc[-1] == 'bullish' if isinstance(medium_term_trend, pd.Series) else False
        )
        
        # Check EMA crossover
        if isinstance(ema20, pd.Series) and isinstance(ema50, pd.Series) and len(ema20) > 1:
            ema_cross_above = (ema20.iloc[-1] > ema50.iloc[-1]) and (ema20.iloc[-2] <= ema50.iloc[-2])
            ema_cross_below = (ema20.iloc[-1] < ema50.iloc[-1]) and (ema20.iloc[-2] >= ema50.iloc[-2])
        else:
            ema_cross_above = ema20_val > ema50_val
            ema_cross_below = ema20_val < ema50_val
        
        # MACD conditions
        macd_positive = macd_line_val > macd_signal_val
        macd_negative = macd_line_val < macd_signal_val
        
        # RSI conditions
        rsi_not_overbought = rsi_val < 70
        rsi_momentum_fading = rsi_val < 50
        
        # Volume confirmation (optional)
        volume_spike = False
        if volume is not None and volume_ma is not None:
            vol_val = volume.iloc[-1] if isinstance(volume, pd.Series) and len(volume) > 0 else (
                volume if not isinstance(volume, pd.Series) else None
            )
            vol_ma_val = volume_ma.iloc[-1] if isinstance(volume_ma, pd.Series) and len(volume_ma) > 0 else (
                volume_ma if not isinstance(volume_ma, pd.Series) else None
            )
            if vol_val is not None and vol_ma_val is not None and not pd.isna(vol_val) and not pd.isna(vol_ma_val):
                volume_spike = vol_val > vol_ma_val * 1.2
        
        # Generate signal
        signal = 'hold'
        confidence = 0.5
        reason_parts = []
        metadata = {}
        
        # BUY SIGNAL
        if (
            is_bullish_long_term and
            is_bullish_medium_term and
            macd_positive and
            rsi_not_overbought and
            (ema_cross_above or ema20_val > ema50_val * 1.02)
        ):
            signal = 'buy'
            confidence = 0.7
            if ema_cross_above:
                reason_parts.append("EMA20 crossed above EMA50")
            reason_parts.append("Trend confirmed (Price > SMA200)")
            reason_parts.append("MACD positive")
            reason_parts.append(f"RSI at {rsi_val:.1f} (not overbought)")
            if volume_spike:
                reason_parts.append("Volume spike confirmed")
                confidence += 0.1
        
        # SELL SIGNAL
        elif (
            (ema_cross_below or not is_bullish_long_term or not is_bullish_medium_term) and
            (macd_negative or rsi_momentum_fading)
        ):
            signal = 'sell'
            confidence = 0.6
            if ema_cross_below:
                reason_parts.append("EMA20 crossed below EMA50")
            if not is_bullish_long_term:
                reason_parts.append("Long-term trend weakening")
            if macd_negative:
                reason_parts.append("MACD backcross (negative)")
            if rsi_momentum_fading:
                reason_parts.append(f"RSI at {rsi_val:.1f} (momentum fading)")
        
        # Default: HOLD
        if signal == 'hold':
            reason_parts.append("Waiting for clearer signals")
            if not is_bullish_long_term:
                reason_parts.append("Long-term trend not bullish")
            if not macd_positive:
                reason_parts.append("MACD not positive")
            if not rsi_not_overbought:
                reason_parts.append("RSI overbought")
        
        reason = ". ".join(reason_parts) if reason_parts else "No clear signal"
        confidence = min(1.0, max(0.0, confidence))
        
        metadata = {
            'ema_cross_above': ema_cross_above,
            'ema_cross_below': ema_cross_below,
            'volume_spike': volume_spike,
            'trend_long_term': 'bullish' if is_bullish_long_term else 'bearish',
            'trend_medium_term': 'bullish' if is_bullish_medium_term else 'bearish',
        }
        
        return StrategyResult(
            signal=signal,
            confidence=confidence,
            reason=reason,
            metadata=metadata,
            strategy_name=self.name
        )

