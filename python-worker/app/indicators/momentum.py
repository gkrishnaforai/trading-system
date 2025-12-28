"""
Momentum indicators: RSI, MACD
"""
import logging
from typing import Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def calculate_rsi(data: pd.Series, window: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI) using Wilder's smoothing method
    Industry standard: Uses exponential moving average (Wilder's smoothing) for gains/losses
    
    Args:
        data: Price series (typically close prices)
        window: Number of periods (default 14)
    
    Returns:
        Series with RSI values (0-100)
    """
    if len(data) < window + 1:
        logger.warning(f"Insufficient data for RSI: {len(data)} < {window + 1}")
        return pd.Series([np.nan] * len(data), index=data.index)
    
    delta = data.diff()
    
    # Separate gains and losses
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Use Wilder's smoothing (exponential moving average with alpha = 1/window)
    # This is the industry standard method for RSI calculation
    # First period: simple average of gains/losses
    # Subsequent periods: EMA with smoothing factor = 1/window
    # Using ewm with alpha=1/window and adjust=False gives Wilder's smoothing
    avg_gain = gain.ewm(alpha=1.0/window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/window, min_periods=window, adjust=False).mean()
    
    # Ensure we have valid values before division
    if avg_loss.isna().all() or (avg_loss == 0).all():
        logger.warning(f"All avg_loss values are zero or NaN for RSI calculation")
        return pd.Series([50.0] * len(data), index=data.index)  # Return neutral RSI
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # Replace infinite values (when avg_loss is 0) with 100
    rsi = rsi.replace([np.inf, -np.inf], 100)
    
    return rsi.fillna(50)  # Fill NaN with neutral value


def calculate_macd(
    data: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate MACD (Moving Average Convergence Divergence)
    
    Args:
        data: Price series (typically close prices)
        fast_period: Fast EMA period (default 12)
        slow_period: Slow EMA period (default 26)
        signal_period: Signal line EMA period (default 9)
    
    Returns:
        Tuple of (MACD line, Signal line, Histogram)
    """
    if len(data) < slow_period + signal_period:
        logger.warning(f"Insufficient data for MACD: {len(data)} < {slow_period + signal_period}")
        nan_series = pd.Series([np.nan] * len(data), index=data.index)
        return nan_series, nan_series, nan_series
    
    ema_fast = data.ewm(span=fast_period, adjust=False).mean()
    ema_slow = data.ewm(span=slow_period, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def calculate_momentum_score(
    data: pd.Series,
    rsi: pd.Series,
    macd_histogram: pd.Series,
    volume: pd.Series,
    volume_ma: pd.Series
) -> pd.Series:
    """
    Calculate composite momentum score (0-100)
    
    Combines RSI, MACD, and volume confirmation
    
    Args:
        data: Price series
        rsi: RSI values
        macd_histogram: MACD histogram values
        volume: Volume series
        volume_ma: Volume moving average
    
    Returns:
        Series with momentum scores (0-100)
    """
    # Normalize RSI to 0-1 scale (50 = neutral)
    rsi_score = (rsi - 50) / 50  # -1 to 1, then normalize
    
    # Normalize MACD histogram (use rolling max for scaling)
    macd_max = macd_histogram.rolling(window=20).max().abs()
    macd_score = macd_histogram / (macd_max + 1e-10)  # Avoid division by zero
    
    # Volume confirmation (1.0 if volume > MA, else 0.5)
    volume_score = (volume > volume_ma).astype(float) * 0.5 + 0.5
    
    # Combine scores (weighted average)
    momentum = (rsi_score * 0.4 + macd_score * 0.4 + volume_score * 0.2) * 50 + 50
    
    # Clamp to 0-100
    momentum = momentum.clip(0, 100)
    
    return momentum

