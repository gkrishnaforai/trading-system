"""
Volatility indicators: ATR, Bollinger Bands
Industry-standard implementations
"""

import logging
from typing import Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# =========================
# ATR — Wilder's Method
# =========================
def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14
) -> pd.Series:
    """
    Calculate Average True Range (ATR) using Wilder's smoothing.
    Industry standard (used by TradingView, ThinkOrSwim, MetaTrader).

    Args:
        high: High prices
        low: Low prices
        close: Close prices
        window: ATR period (default 14)

    Returns:
        ATR series
    """

    if len(high) < window:
        logger.warning(f"Insufficient data for ATR: {len(high)} < {window}")
        return pd.Series(np.nan, index=high.index)

    # Ensure aligned indices
    high, low = high.align(low, join="inner")
    high, close = high.align(close, join="inner")
    low, close = low.align(close, join="inner")

    # True Range components
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing (EMA with alpha = 1/window)
    atr = true_range.ewm(
        alpha=1.0 / window,
        min_periods=window,
        adjust=False
    ).mean()

    return atr


# =========================
# Bollinger Bands
# =========================
def calculate_bollinger_bands(
    data: pd.Series,
    window: int = 20,
    num_std: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands using population standard deviation (ddof=0).
    Matches TradingView / Bloomberg behavior.

    Args:
        data: Price series (usually close)
        window: Lookback period (default 20)
        num_std: Number of standard deviations (default 2)

    Returns:
        upper_band, middle_band, lower_band
    """

    if len(data) < window:
        logger.warning(f"Insufficient data for Bollinger Bands: {len(data)} < {window}")
        nan = pd.Series(np.nan, index=data.index)
        return nan, nan, nan

    # Rolling mean
    middle_band = data.rolling(window=window, min_periods=window).mean()

    # Population standard deviation (ddof=0)
    std = data.rolling(
        window=window,
        min_periods=window
    ).std(ddof=0)

    upper_band = middle_band + (std * num_std)
    lower_band = middle_band - (std * num_std)

    return upper_band, middle_band, lower_band


# =========================
# Optional Utility (Recommended)
# =========================
def calculate_bollinger_bandwidth(
    upper_band: pd.Series,
    lower_band: pd.Series,
    middle_band: pd.Series
) -> pd.Series:
    """
    Bollinger Band Width — detects volatility expansion / squeeze.
    """

    bandwidth = (upper_band - lower_band) / middle_band
    return bandwidth
