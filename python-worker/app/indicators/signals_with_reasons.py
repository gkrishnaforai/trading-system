"""
Extended signal generation with reasons for buy/sell/hold decisions.
"""

import logging
from typing import Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def generate_signals_with_reasons(
    price: pd.Series,
    ema20: pd.Series,
    ema50: pd.Series,
    sma200: pd.Series,
    macd_line: pd.Series,
    macd_signal: pd.Series,
    macd_histogram: pd.Series,
    rsi: pd.Series,
    volume: pd.Series,
    volume_ma: pd.Series,
    long_term_trend: pd.Series,
    medium_term_trend: pd.Series,
) -> pd.DataFrame:
    """
    Generate trading signals with detailed reasons.
    
    Returns DataFrame with signal and reason columns.
    """
    signals = pd.Series('hold', index=price.index)
    reasons = pd.Series('', index=price.index)
    
    # Ensure all series have the same index
    if not all(len(s) == len(price) for s in [ema20, ema50, sma200, macd_line, rsi]):
        logger.warning("Series length mismatch in signal generation")
        return pd.DataFrame({'signal': signals, 'reason': reasons})
    
    # Calculate EMA crossovers
    ema_cross_above = (ema20 > ema50) & (ema20.shift(1) <= ema50.shift(1))
    ema_cross_below = (ema20 < ema50) & (ema20.shift(1) >= ema50.shift(1))
    
    # Volume confirmation
    volume_spike = volume > volume_ma * 1.2
    
    for i in range(1, len(price)):
        # Skip if we don't have enough data
        if pd.isna(price.iloc[i]) or pd.isna(ema20.iloc[i]) or pd.isna(ema50.iloc[i]):
            continue
        
        # Long-term trend check (Golden Cross)
        is_bullish_long_term = long_term_trend.iloc[i] == 'bullish'
        is_bullish_medium_term = medium_term_trend.iloc[i] == 'bullish'
        
        # MACD confirmation
        macd_positive = macd_line.iloc[i] > macd_signal.iloc[i]
        macd_negative = macd_line.iloc[i] < macd_signal.iloc[i]
        
        # RSI conditions
        rsi_not_overbought = rsi.iloc[i] < 70
        rsi_not_oversold = rsi.iloc[i] > 30
        rsi_oversold = rsi.iloc[i] < 30
        rsi_overbought = rsi.iloc[i] > 70
        
        # BUY SIGNAL CONDITIONS
        ema_cross_occurred = ema_cross_above.iloc[i]
        has_volume_confirmation = volume_spike.iloc[i] if i < len(volume_spike) else True
        
        buy_reasons = []
        if is_bullish_long_term:
            buy_reasons.append("Price > SMA200 (bullish long-term)")
        if is_bullish_medium_term:
            buy_reasons.append("EMA20 > SMA50 (bullish medium-term)")
        if macd_positive:
            buy_reasons.append("MACD above signal (positive momentum)")
        if rsi_not_overbought:
            buy_reasons.append("RSI < 70 (not overbought)")
        if ema_cross_occurred:
            buy_reasons.append("EMA20 crossed above EMA50")
        elif ema20.iloc[i] > ema50.iloc[i] * 1.02:
            buy_reasons.append("EMA20 significantly above EMA50")
        if has_volume_confirmation:
            buy_reasons.append("Volume spike confirmation")
        
        if len(buy_reasons) >= 4:  # Require at least 4 conditions
            signals.iloc[i] = 'buy'
            reasons.iloc[i] = '; '.join(buy_reasons)
        
        # SELL SIGNAL CONDITIONS
        sell_reasons = []
        ema_cross_below_occurred = ema_cross_below.iloc[i]
        momentum_fading = macd_negative or rsi.iloc[i] < 50
        trend_weakening = not is_bullish_long_term or not is_bullish_medium_term
        
        if ema_cross_below_occurred:
            sell_reasons.append("EMA20 crossed below EMA50")
        if trend_weakening:
            sell_reasons.append("Trend weakening (price below SMA200 or EMA20 < SMA50)")
        if macd_negative:
            sell_reasons.append("MACD below signal (negative momentum)")
        if rsi.iloc[i] < 50:
            sell_reasons.append("RSI < 50 (momentum fading)")
        if rsi_overbought:
            sell_reasons.append("RSI > 70 (overbought)")
        
        if len(sell_reasons) >= 2:  # Require at least 2 conditions
            signals.iloc[i] = 'sell'
            reasons.iloc[i] = '; '.join(sell_reasons)
        
        # HOLD: default remains unless overwritten
        
        # Special HOLD conditions with reasons
        if signals.iloc[i] == 'hold':
            hold_reasons = []
            if rsi_oversold:
                hold_reasons.append("RSI oversold (<30) - potential reversal")
            elif rsi_overbought:
                hold_reasons.append("RSI overbought (>70) - wait for pullback")
            elif not is_bullish_long_term and not is_bullish_medium_term:
                hold_reasons.append("No clear trend established")
            else:
                hold_reasons.append("Neutral conditions")
            reasons.iloc[i] = '; '.join(hold_reasons)
    
    return pd.DataFrame({'signal': signals, 'reason': reasons})
