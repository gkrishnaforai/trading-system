"""
Momentum indicators: RSI, MACD, Composite Momentum Score
Aligned with BUY-IN-FEAR / SELL-IN-GREED philosophy
"""

import logging
from typing import Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# =========================
# RSI CALCULATION (FIXED)
# =========================
def calculate_rsi(data: pd.Series, window: int = 14) -> pd.Series:
    """
    Calculate RSI using Wilder's smoothing (industry standard)

    IMPORTANT FIXES:
    - Do NOT force-fill RSI with 50 (hides fear)
    - Preserve NaNs early
    """

    if len(data) < window + 1:
        logger.warning("Insufficient data for RSI calculation")
        return pd.Series(np.nan, index=data.index)

    delta = data.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # Handle divide-by-zero (true strength → RSI = 100)
    rsi = rsi.replace([np.inf, -np.inf], 100)

    return rsi


# =========================
# MACD CALCULATION (OK)
# =========================
def calculate_macd(
    data: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:

    if len(data) < slow_period + signal_period:
        logger.warning("Insufficient data for MACD calculation")
        nan = pd.Series(np.nan, index=data.index)
        return nan, nan, nan

    ema_fast = data.ewm(span=fast_period, adjust=False).mean()
    ema_slow = data.ewm(span=slow_period, adjust=False).mean()

    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


# =====================================
# COMPOSITE MOMENTUM SCORE (FIXED)
# =====================================
def calculate_momentum_score(
    price: pd.Series,
    rsi: pd.Series,
    macd_histogram: pd.Series,
    volume: pd.Series,
    volume_ma: pd.Series
) -> pd.Series:
    """
    Momentum Score (0–100)

    FIXES:
    - Non-linear fear/greed handling
    - Proper MACD scaling
    - Volume capitulation recognition
    """

    # ---- RSI COMPONENT (FEAR SENSITIVE)
    # Fear matters more than greed
    rsi_score = np.where(
        rsi < 50,
        (rsi - 50) / 30,   # amplify fear
        (rsi - 50) / 50   # dampen greed
    )
    rsi_score = pd.Series(rsi_score, index=price.index).clip(-1, 1)

    # ---- MACD COMPONENT (STABILITY FIX)
    macd_std = macd_histogram.rolling(20).std()
    macd_score = macd_histogram / (macd_std + 1e-6)
    macd_score = macd_score.clip(-2, 2) / 2  # normalize to -1 → +1

    # ---- VOLUME COMPONENT (CAPITULATION AWARE)
    volume_ratio = volume / (volume_ma + 1e-6)

    volume_score = np.where(
        volume_ratio >= 2.0, 1.0,          # panic / institutional activity
        np.where(volume_ratio >= 1.2, 0.5,  # confirmation
                 -0.3)                     # weak / complacent
    )

    volume_score = pd.Series(volume_score, index=price.index)

    # ---- COMBINE (FEAR WEIGHTED)
    momentum_raw = (
        0.45 * rsi_score +
        0.35 * macd_score +
        0.20 * volume_score
    )

    # Map to 0–100 scale
    momentum_score = (momentum_raw + 1) * 50

    return momentum_score.clip(0, 100)
