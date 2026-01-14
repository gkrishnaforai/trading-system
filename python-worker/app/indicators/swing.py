"""
Swing Trading Specific Indicators
ADX, Stochastic, Williams %R, VWAP, Fibonacci Retracements
Industry-standard, production-safe implementations
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional

from app.exceptions import ValidationError


# =========================
# ADX — Correct Wilder Method
# =========================
def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Dict[str, pd.Series]:

    if high is None or low is None or close is None:
        raise ValidationError("High, low, close required")

    if len(high) < period + 1:
        raise ValidationError(f"Need at least {period + 1} periods")

    # Align series
    high, low, close = high.align(low, join="inner")
    high, close = high.align(close, join="inner")

    # True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    # Directional Movement (correct definition)
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    # Wilder smoothing
    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr

    # DX and ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    dx = dx.replace([np.inf, -np.inf], np.nan)

    adx = dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

    return {
        "adx": adx,
        "di_plus": plus_di,
        "di_minus": minus_di
    }


# =========================
# Stochastic Oscillator
# =========================
def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> Dict[str, pd.Series]:

    if len(high) < k_period:
        raise ValidationError(f"Need at least {k_period} periods")

    lowest_low = low.rolling(k_period, min_periods=k_period).min()
    highest_high = high.rolling(k_period, min_periods=k_period).max()

    range_ = highest_high - lowest_low
    range_ = range_.replace(0, np.nan)

    k = 100 * (close - lowest_low) / range_
    d = k.rolling(d_period, min_periods=d_period).mean()

    return {
        "stochastic_k": k,
        "stochastic_d": d
    }


# =========================
# Williams %R
# =========================
def calculate_williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:

    if len(high) < period:
        raise ValidationError(f"Need at least {period} periods")

    highest_high = high.rolling(period, min_periods=period).max()
    lowest_low = low.rolling(period, min_periods=period).min()

    range_ = highest_high - lowest_low
    range_ = range_.replace(0, np.nan)

    wr = -100 * (highest_high - close) / range_
    return wr


# =========================
# VWAP — Correct Implementation
# =========================
def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: Optional[int] = None
) -> pd.Series:

    if any(x is None for x in [high, low, close, volume]):
        raise ValidationError("High, low, close, volume required")

    typical_price = (high + low + close) / 3
    pv = typical_price * volume

    volume = volume.replace(0, np.nan)

    if period:
        vwap = pv.rolling(period, min_periods=period).sum() / volume.rolling(period, min_periods=period).sum()
    else:
        # Session VWAP (cumulative)
        vwap = pv.cumsum() / volume.cumsum()

    return vwap


# =========================
# Fibonacci Retracements
# =========================
def calculate_fibonacci_retracements(
    high: pd.Series,
    low: pd.Series,
    period: int = 20
) -> Dict[str, pd.Series]:

    if len(high) < period:
        raise ValidationError(f"Need at least {period} periods")

    swing_high = high.rolling(period, min_periods=period).max()
    swing_low = low.rolling(period, min_periods=period).min()

    diff = swing_high - swing_low

    return {
        "fib_382": swing_high - diff * 0.382,
        "fib_500": swing_high - diff * 0.500,
        "fib_618": swing_high - diff * 0.618
    }
