"""
Trend detection indicators
Robust, slope-aware, low-noise trend classification
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# =========================
# Utility: Slope calculation
# =========================
def _slope(series: pd.Series, lookback: int = 5) -> pd.Series:
    """
    Calculate simple slope over N periods
    """
    return (series - series.shift(lookback)) / lookback


# =========================
# Long-Term Trend (Price vs SMA200)
# =========================
def detect_long_term_trend(
    price: pd.Series,
    sma200: pd.Series,
    buffer_pct: float = 0.02,   # 2% buffer zone
    slope_lookback: int = 5
) -> pd.Series:
    """
    Detect long-term trend using price, SMA200, and SMA slope
    
    Regimes:
    - bullish: price above SMA200 + rising SMA200
    - bearish: price below SMA200 + falling SMA200
    - neutral: transition / chop
    
    Returns:
        Series of 'bullish', 'bearish', 'neutral'
    """

    if len(price) != len(sma200):
        logger.warning("Price and SMA200 length mismatch")
        return pd.Series("neutral", index=price.index)

    trend = pd.Series("neutral", index=price.index)

    # Distance from SMA
    distance = (price - sma200) / sma200

    # SMA slope
    sma_slope = _slope(sma200, slope_lookback)

    bullish = (
        (distance > buffer_pct) &
        (sma_slope > 0)
    )

    bearish = (
        (distance < -buffer_pct) &
        (sma_slope < 0)
    )

    trend[bullish] = "bullish"
    trend[bearish] = "bearish"

    return trend


# =========================
# Medium-Term Trend (EMA20 vs SMA50)
# =========================
def detect_medium_term_trend(
    ema20: pd.Series,
    sma50: pd.Series,
    buffer_pct: float = 0.01,   # tighter buffer for swing trades
    slope_lookback: int = 3
) -> pd.Series:
    """
    Detect medium-term trend using EMA20 vs SMA50 with slope confirmation
    
    Regimes:
    - bullish: EMA20 > SMA50 + both rising
    - bearish: EMA20 < SMA50 + both falling
    - neutral: consolidation / pullback
    
    Returns:
        Series of 'bullish', 'bearish', 'neutral'
    """

    if len(ema20) != len(sma50):
        logger.warning("EMA20 and SMA50 length mismatch")
        return pd.Series("neutral", index=ema20.index)

    trend = pd.Series("neutral", index=ema20.index)

    # Relative distance
    distance = (ema20 - sma50) / sma50

    ema_slope = _slope(ema20, slope_lookback)
    sma_slope = _slope(sma50, slope_lookback)

    bullish = (
        (distance > buffer_pct) &
        (ema_slope > 0) &
        (sma_slope > 0)
    )

    bearish = (
        (distance < -buffer_pct) &
        (ema_slope < 0) &
        (sma_slope < 0)
    )

    trend[bullish] = "bullish"
    trend[bearish] = "bearish"

    return trend
