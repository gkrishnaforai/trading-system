"""
Trading signal generation based on indicators
Improved: vectorized, safer, no signal spam, fear/greed aligned
"""

import logging
from typing import Optional, Dict, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# ============================
# Core Signal Generator
# ============================

def generate_signal(
    price: pd.Series,
    ema20: pd.Series,
    ema50: pd.Series,
    sma200: pd.Series,
    macd_line: pd.Series,
    macd_signal: pd.Series,
    rsi: pd.Series,
    volume: pd.Series,
    volume_ma: pd.Series,
    long_term_trend: pd.Series,
    medium_term_trend: pd.Series,
) -> pd.Series:
    """
    Generates BUY / SELL / HOLD signals with:
    - No look-ahead bias
    - No repeated signals
    - Buy in fear, sell in greed logic
    """

    index = price.index
    signals = pd.Series("hold", index=index)

    # ============================
    # Safety checks
    # ============================
    required = [
        ema20, ema50, sma200,
        macd_line, macd_signal,
        rsi, volume, volume_ma,
        long_term_trend, medium_term_trend
    ]

    if not all(len(s) == len(price) for s in required):
        logger.warning("Signal generation skipped: length mismatch")
        return signals

    # ============================
    # Trend & Momentum Conditions
    # ============================

    bullish_long = long_term_trend == "bullish"
    bullish_medium = medium_term_trend == "bullish"

    ema_cross_up = (ema20 > ema50) & (ema20.shift(1) <= ema50.shift(1))
    ema_cross_down = (ema20 < ema50) & (ema20.shift(1) >= ema50.shift(1))

    macd_score = np.where(macd_line > macd_signal, 0.25, 0.0)
    macd_negative = macd_line < macd_signal

    volume_spike = volume > volume_ma * 1.2

    # ============================
    # FEAR CONDITIONS (BUY)
    # ============================

    rsi_fear_zone = (rsi >= 40) & (rsi <= 55)
    pullback_zone = price <= ema20 * 1.01

    buy_setup = (
        bullish_long &
        bullish_medium &
        macd_positive &
        rsi_fear_zone &
        (ema_cross_up | pullback_zone)
    )

    # ============================
    # GREED CONDITIONS (SELL)
    # ============================

    rsi_greed_zone = rsi >= 70
    momentum_fading = macd_negative | (rsi < 50)
    trend_breakdown = (~bullish_long) | (~bullish_medium)

    sell_setup = (
        (ema_cross_down | rsi_greed_zone | trend_breakdown) &
        momentum_fading
    )

    # ============================
    # Signal De-duplication
    # ============================

    position = "flat"

    for i in range(1, len(price)):
        if position == "flat" and buy_setup.iloc[i]:
            signals.iloc[i] = "buy"
            position = "long"

        elif position == "long" and sell_setup.iloc[i]:
            signals.iloc[i] = "sell"
            position = "flat"

    return signals


# ============================
# Pullback Zones
# ============================

def calculate_pullback_zones(
    price: pd.Series,
    ema20: pd.Series,
    atr: pd.Series,
    trend: Optional[pd.Series] = None
) -> Tuple[pd.Series, pd.Series]:
    """
    EMA ± ATR pullback zone with trend context
    Returns two Series: lower_zone and upper_zone
    """
    if len(ema20) == 0 or len(atr) == 0 or len(price) == 0:
        return pd.Series([None] * len(price), index=price.index), pd.Series([None] * len(price), index=price.index)

    # Initialize Series with same index as input
    lower_zone = pd.Series([None] * len(price), index=price.index)
    upper_zone = pd.Series([None] * len(price), index=price.index)
    
    # Calculate for each point
    for i in range(len(price)):
        if i < len(ema20) and i < len(atr):
            ema = ema20.iloc[i]
            atr_val = atr.iloc[i]
            
            if pd.isna(ema) or pd.isna(atr_val):
                continue
                
            # Basic pullback zone: EMA ± ATR
            lower_val = ema - atr_val
            upper_val = ema + atr_val
            
            # Adjust zones based on trend if provided
            if trend is not None and i < len(trend):
                current_trend = trend.iloc[i]
                if current_trend == 'bullish':
                    # In bullish trend, focus on upper zone for entries
                    lower_val = ema - (atr_val * 0.5)  # Tighter lower bound
                    upper_val = ema + (atr_val * 1.5)  # Wider upper bound
                elif current_trend == 'bearish':
                    # In bearish trend, focus on lower zone for entries
                    lower_val = ema - (atr_val * 1.5)  # Wider lower bound
                    upper_val = ema + (atr_val * 0.5)  # Tighter upper bound
            
            lower_zone.iloc[i] = lower_val
            upper_zone.iloc[i] = upper_val

    return lower_zone, upper_zone


# ============================
# ATR Stop Loss
# ============================

def calculate_stop_loss(
    price: pd.Series,
    atr: pd.Series,
    multiplier: float = 2.0,
    position_type: str = "long"
) -> Optional[float]:
    """
    ATR-based stop loss
    """

    if len(price) == 0 or len(atr) == 0:
        return None

    p = price.iloc[-1]
    a = atr.iloc[-1]

    if pd.isna(p) or pd.isna(a):
        return None

    if position_type == "long":
        return float(p - multiplier * a)
    else:
        return float(p + multiplier * a)
