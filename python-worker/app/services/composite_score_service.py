"""
Composite Score Service for Pro Tier
Calculates unified decision scores (0-100) combining trend, momentum, and confirmation
"""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from app.services.base import BaseService
from app.utils.series_utils import extract_latest_value
from app.exceptions import ValidationError


class CompositeScoreService(BaseService):
    """
    Calculates composite scores for Pro tier users
    Provides unified decision engine with trend, momentum, and confirmation scores
    
    SOLID: Single Responsibility - only calculates composite scores
    """
    
    def __init__(self):
        """Initialize composite score service"""
        super().__init__()
    
    def calculate_composite_score(
        self,
        indicators: Dict[str, Any],
        current_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate composite score (0-100) with breakdown
        
        Args:
            indicators: Dictionary of calculated indicators
            current_price: Current stock price (optional, will use latest from price series)
        
        Returns:
            Dictionary with:
            - composite_score: Overall score (0-100)
            - trend_score: Trend strength (0-100)
            - momentum_score: Momentum strength (0-100)
            - confirmation_score: Confirmation strength (0-100)
            - explanation: Human-readable explanation
        """
        # Extract indicators
        price = indicators.get('price')
        ema20 = indicators.get('ema20')
        ema50 = indicators.get('ema50')
        sma200 = indicators.get('sma200')
        macd_line = indicators.get('macd_line')
        macd_signal = indicators.get('macd_signal')
        macd_histogram = indicators.get('macd_histogram')
        rsi = indicators.get('rsi')
        volume = indicators.get('volume')
        volume_ma = indicators.get('volume_ma')
        long_term_trend = indicators.get('long_term_trend')
        medium_term_trend = indicators.get('medium_term_trend')
        
        # Get latest values using utility (DRY)
        price_val = extract_latest_value(price, current_price)
        
        if price_val is None:
            return {
                'composite_score': 50,
                'trend_score': 50,
                'momentum_score': 50,
                'confirmation_score': 50,
                'explanation': 'Insufficient data for score calculation'
            }
        
        # Calculate Trend Score (0-100)
        trend_score = self._calculate_trend_score(
            price_val, ema20, ema50, sma200, long_term_trend, medium_term_trend
        )
        
        # Calculate Momentum Score (0-100)
        momentum_score = self._calculate_momentum_score(
            rsi, macd_line, macd_signal, macd_histogram
        )
        
        # Calculate Confirmation Score (0-100)
        confirmation_score = self._calculate_confirmation_score(
            ema20, ema50, volume, volume_ma, macd_line, macd_signal
        )
        
        # Composite Score: Weighted average
        # Trend: 40%, Momentum: 35%, Confirmation: 25%
        composite_score = (
            trend_score * 0.40 +
            momentum_score * 0.35 +
            confirmation_score * 0.25
        )
        
        # Generate explanation
        explanation = self._generate_explanation(
            composite_score, trend_score, momentum_score, confirmation_score,
            price_val, ema20, ema50, sma200, rsi, macd_line, macd_signal,
            long_term_trend, medium_term_trend
        )
        
        return {
            'composite_score': round(composite_score, 1),
            'trend_score': round(trend_score, 1),
            'momentum_score': round(momentum_score, 1),
            'confirmation_score': round(confirmation_score, 1),
            'explanation': explanation
        }
    
    def _calculate_trend_score(
        self,
        price: float,
        ema20: Any,
        ema50: Any,
        sma200: Any,
        long_term_trend: Any,
        medium_term_trend: Any
    ) -> float:
        """Calculate trend strength score (0-100)"""
        score = 50  # Start neutral
        
        # Get latest values using utility (DRY)
        ema20_val = extract_latest_value(ema20)
        ema50_val = extract_latest_value(ema50)
        sma200_val = extract_latest_value(sma200)
        
        # Long-term trend (40 points)
        if long_term_trend:
            trend_val = long_term_trend.iloc[-1] if isinstance(long_term_trend, pd.Series) else long_term_trend
            if trend_val == 'bullish' and sma200_val and price > sma200_val:
                score += 20
            elif trend_val == 'bearish' or (sma200_val and price < sma200_val):
                score -= 20
        
        # Medium-term trend (30 points)
        if medium_term_trend:
            trend_val = medium_term_trend.iloc[-1] if isinstance(medium_term_trend, pd.Series) else medium_term_trend
            if trend_val == 'bullish' and ema20_val and ema50_val and ema20_val > ema50_val:
                score += 15
            elif trend_val == 'bearish' or (ema20_val and ema50_val and ema20_val < ema50_val):
                score -= 15
        
        # EMA alignment (30 points)
        if ema20_val and ema50_val and sma200_val:
            # Bullish alignment: EMA20 > EMA50 > SMA200
            if ema20_val > ema50_val > sma200_val:
                score += 15
            # Bearish alignment: EMA20 < EMA50 < SMA200
            elif ema20_val < ema50_val < sma200_val:
                score -= 15
        
        return max(0, min(100, score))
    
    def _calculate_momentum_score(
        self,
        rsi: Any,
        macd_line: Any,
        macd_signal: Any,
        macd_histogram: Any
    ) -> float:
        """Calculate momentum strength score (0-100)"""
        score = 50  # Start neutral
        
        # Get latest values using utility (DRY)
        rsi_val = extract_latest_value(rsi)
        macd_line_val = extract_latest_value(macd_line)
        macd_signal_val = extract_latest_value(macd_signal)
        macd_hist_val = extract_latest_value(macd_histogram)
        
        # RSI contribution (40 points)
        if rsi_val and not pd.isna(rsi_val):
            if 30 < rsi_val < 70:  # Healthy momentum zone
                # Closer to 50 = neutral, closer to extremes = stronger
                if rsi_val > 50:
                    score += (rsi_val - 50) / 20 * 20  # Up to +20 for RSI 70
                else:
                    score += (rsi_val - 50) / 20 * 20  # Down to -20 for RSI 30
            elif rsi_val >= 70:  # Overbought
                score -= 20
            elif rsi_val <= 30:  # Oversold (could be bullish reversal)
                score += 10
        
        # MACD contribution (60 points)
        if macd_line_val and macd_signal_val and not pd.isna(macd_line_val) and not pd.isna(macd_signal_val):
            if macd_line_val > macd_signal_val:
                # Positive momentum
                if macd_hist_val and macd_hist_val > 0:
                    score += min(30, macd_hist_val * 10)  # Scale histogram
                else:
                    score += 15
            else:
                # Negative momentum
                score -= 20
        
        return max(0, min(100, score))
    
    def _calculate_confirmation_score(
        self,
        ema20: Any,
        ema50: Any,
        volume: Any,
        volume_ma: Any,
        macd_line: Any,
        macd_signal: Any
    ) -> float:
        """Calculate confirmation strength score (0-100)"""
        score = 50  # Start neutral
        
        # Get latest values using utility (DRY)
        ema20_val = extract_latest_value(ema20)
        ema50_val = extract_latest_value(ema50)
        
        # EMA crossover confirmation (40 points)
        if ema20_val and ema50_val:
            if isinstance(ema20, pd.Series) and isinstance(ema50, pd.Series) and len(ema20) > 1:
                # Check for recent crossover
                ema_cross_above = (ema20.iloc[-1] > ema50.iloc[-1]) and (ema20.iloc[-2] <= ema50.iloc[-2])
                ema_cross_below = (ema20.iloc[-1] < ema50.iloc[-1]) and (ema20.iloc[-2] >= ema50.iloc[-2])
                
                if ema_cross_above:
                    score += 20
                elif ema_cross_below:
                    score -= 20
                elif ema20_val > ema50_val:
                    score += 10
                else:
                    score -= 10
        
        # Volume confirmation (30 points)
        if volume and volume_ma:
            vol_val = volume.iloc[-1] if isinstance(volume, pd.Series) else volume
            vol_ma_val = volume_ma.iloc[-1] if isinstance(volume_ma, pd.Series) else volume_ma
            
            if vol_val and vol_ma_val and vol_val > vol_ma_val * 1.2:
                score += 15  # Volume spike
            elif vol_val and vol_ma_val and vol_val < vol_ma_val * 0.8:
                score -= 10  # Low volume
        
        # MACD confirmation (30 points)
        if macd_line and macd_signal:
            macd_line_val = macd_line.iloc[-1] if isinstance(macd_line, pd.Series) else macd_line
            macd_signal_val = macd_signal.iloc[-1] if isinstance(macd_signal, pd.Series) else macd_signal
            
            if macd_line_val and macd_signal_val:
                if macd_line_val > macd_signal_val:
                    score += 15
                else:
                    score -= 15
        
        return max(0, min(100, score))
    
    def _generate_explanation(
        self,
        composite_score: float,
        trend_score: float,
        momentum_score: float,
        confirmation_score: float,
        price: float,
        ema20: Any,
        ema50: Any,
        sma200: Any,
        rsi: Any,
        macd_line: Any,
        macd_signal: Any,
        long_term_trend: Any,
        medium_term_trend: Any
    ) -> str:
        """Generate human-readable explanation"""
        # Get latest values using utility (DRY)
        rsi_val = extract_latest_value(rsi)
        macd_line_val = extract_latest_value(macd_line)
        macd_signal_val = extract_latest_value(macd_signal)
        
        # Determine signal
        if composite_score >= 70:
            signal = "BUY"
        elif composite_score <= 30:
            signal = "SELL"
        else:
            signal = "HOLD"
        
        explanation_parts = [f"{signal} ({int(composite_score)}/100)"]
        
        # Trend explanation
        if trend_score >= 60:
            explanation_parts.append("Trend strong")
            if sma200:
                sma200_val = sma200.iloc[-1] if isinstance(sma200, pd.Series) else sma200
                if sma200_val and price > sma200_val:
                    explanation_parts.append("(200-MA support)")
        elif trend_score <= 40:
            explanation_parts.append("Trend weak")
        
        # Momentum explanation
        if momentum_score >= 60:
            explanation_parts.append("EMA20 crossed above EMA50")
        if macd_line_val and macd_signal_val and macd_line_val > macd_signal_val:
            explanation_parts.append("MACD positive")
        if rsi_val:
            explanation_parts.append(f"RSI {rsi_val:.0f} (healthy)" if 30 < rsi_val < 70 else f"RSI {rsi_val:.0f}")
        
        return ". ".join(explanation_parts)

