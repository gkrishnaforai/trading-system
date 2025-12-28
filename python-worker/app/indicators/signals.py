"""
Trading signal generation based on indicators
Implements the business logic for buy/sell/hold signals
"""
import logging
from typing import Optional, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def generate_signal(
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
    medium_term_trend: pd.Series
) -> pd.Series:
    """
    Generate buy/sell/hold signals based on comprehensive analysis
    
    Strategy Implementation:
    - Long-term trend: Price > 200-day SMA (Golden Cross)
    - Medium-term trend: EMA20 vs SMA50 for trend context
    - Buy Signal Requirements:
      1. Short EMA (EMA20) crosses above long EMA (EMA50)
      2. Trend direction confirmed: Price > SMA200 (long-term bullish)
      3. MACD moving positive (MACD line > Signal line)
      4. RSI not overbought (< 70)
      5. Volume spike confirmation (volume > 1.2x volume MA)
    - Sell Signal Requirements:
      1. Short EMA (EMA20) crosses below long EMA (EMA50)
      2. Momentum fading: MACD backcross (MACD < Signal) OR RSI drops below 50
      3. Trend weakening (long-term or medium-term trend not bullish)
    
    Confirmation Filters:
    - Volume spikes on crossover
    - Pullback to EMA in confirmed trend (calculated separately)
    - Momentum indicators (RSI/MACD) aligned with trend
    
    Returns:
        Series with 'buy', 'sell', or 'hold'
    """
    signals = pd.Series('hold', index=price.index)
    
    # Ensure all series have the same index
    if not all(len(s) == len(price) for s in [ema20, ema50, sma200, macd_line, rsi]):
        logger.warning("Series length mismatch in signal generation")
        return signals
    
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
        
        # BUY SIGNAL CONDITIONS
        # All conditions must be met:
        # 1. Short EMA crosses above long EMA (EMA20 > EMA50 crossover)
        # 2. Long-term trend confirmed (Price > SMA200)
        # 3. MACD moving positive (MACD line > Signal line)
        # 4. RSI not overbought (< 70)
        # 5. Volume spike confirmation (optional but preferred)
        ema_cross_occurred = ema_cross_above.iloc[i]
        has_volume_confirmation = volume_spike.iloc[i] if i < len(volume_spike) else True
        
        if (
            is_bullish_long_term and  # 1. Price > SMA200 (Golden Cross / long-term trend confirmed)
            is_bullish_medium_term and  # 2. EMA20 > SMA50 (medium-term trend context)
            macd_positive and  # 3. MACD above signal (momentum positive)
            rsi_not_overbought and  # 4. RSI < 70 (not overbought)
            (ema_cross_occurred or (ema20.iloc[i] > ema50.iloc[i] * 1.02))  # 5. EMA crossover or strong position
            # Note: Volume spike is calculated but not strictly required for buy signal
            # to allow signals in low-volume environments. Can be added as strict requirement if needed.
        ):
            signals.iloc[i] = 'buy'
        
        # SELL SIGNAL CONDITIONS
        # Conditions for sell signal:
        # 1. Short EMA crosses below long EMA (EMA20 < EMA50)
        # 2. Momentum fading: MACD backcross (MACD < Signal) OR RSI drops below 50
        # 3. Trend weakening (long-term or medium-term not bullish)
        ema_cross_below_occurred = ema_cross_below.iloc[i]
        momentum_fading = macd_negative or rsi.iloc[i] < 50
        trend_weakening = not is_bullish_long_term or not is_bullish_medium_term
        
        if (
            (ema_cross_below_occurred or trend_weakening) and  # EMA cross below OR trend weakening
            momentum_fading  # MACD backcross OR RSI < 50 (momentum fading)
        ):
            signals.iloc[i] = 'sell'
        
        # Default is 'hold'
    
    return signals


def calculate_pullback_zones(
    price: pd.Series,
    ema20: pd.Series,
    atr: pd.Series,
    trend: Optional[pd.Series] = None
) -> dict:
    """
    Calculate pullback zones for entry
    
    In bullish trends: pullback zone is EMA20 ± ATR
    In bearish trends: pullback zone is EMA20 ± ATR (for short entries)
    
    Args:
        price: Price series
        ema20: 20-period EMA
        atr: Average True Range
        trend: Optional trend series (not used in calculation but kept for compatibility)
    
    Returns:
        Dictionary with 'lower' and 'upper' keys containing latest values
    """
    # Get latest values
    if isinstance(ema20, pd.Series):
        ema20_val = ema20.iloc[-1] if len(ema20) > 0 else None
    else:
        ema20_val = ema20
    
    if isinstance(atr, pd.Series):
        atr_val = atr.iloc[-1] if len(atr) > 0 else None
    else:
        atr_val = atr
    
    if ema20_val is None or atr_val is None or pd.isna(ema20_val) or pd.isna(atr_val):
        return {'lower': None, 'upper': None}
    
    lower_zone = ema20_val - atr_val
    upper_zone = ema20_val + atr_val
    
    return {'lower': lower_zone, 'upper': upper_zone}


def calculate_stop_loss(
    price: pd.Series,
    atr: pd.Series,
    multiplier: float = 2.0,
    position_type: str = 'long'
) -> float:
    """
    Calculate ATR-based stop loss
    
    For long positions: stop_loss = price - (multiplier * ATR)
    For short positions: stop_loss = price + (multiplier * ATR)
    
    Args:
        price: Current price (Series or float)
        atr: Average True Range (Series or float)
        multiplier: ATR multiplier (default 2.0)
        position_type: 'long' or 'short'
    
    Returns:
        Stop loss price (float)
    """
    # Get latest values
    if isinstance(price, pd.Series):
        price_val = price.iloc[-1] if len(price) > 0 else None
    else:
        price_val = price
    
    if isinstance(atr, pd.Series):
        atr_val = atr.iloc[-1] if len(atr) > 0 else None
    else:
        atr_val = atr
    
    if price_val is None or atr_val is None or pd.isna(price_val) or pd.isna(atr_val):
        return None
    
    if position_type == 'long':
        stop_loss = price_val - (atr_val * multiplier)
    else:  # short
        stop_loss = price_val + (atr_val * multiplier)
    
    return float(stop_loss)

