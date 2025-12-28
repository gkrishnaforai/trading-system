"""
Volatility indicators: ATR, Bollinger Bands
"""
import logging
from typing import Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = 14
) -> pd.Series:
    """
    Calculate Average True Range (ATR)
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        window: Number of periods (default 14)
    
    Returns:
        Series with ATR values
    """
    if len(high) < window + 1:
        logger.warning(f"Insufficient data for ATR: {len(high)} < {window + 1}")
        return pd.Series([np.nan] * len(high), index=high.index)
    
    # Calculate True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate ATR as moving average of TR
    atr = tr.rolling(window=window).mean()
    
    return atr


def calculate_bollinger_bands(
    data: pd.Series,
    window: int = 20,
    num_std: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands
    
    Args:
        data: Price series (typically close prices)
        window: Number of periods (default 20)
        num_std: Number of standard deviations (default 2.0)
    
    Returns:
        Tuple of (upper_band, middle_band, lower_band)
    """
    if len(data) < window:
        logger.warning(f"Insufficient data for Bollinger Bands: {len(data)} < {window}")
        nan_series = pd.Series([np.nan] * len(data), index=data.index)
        return nan_series, nan_series, nan_series
    
    middle_band = data.rolling(window=window).mean()
    std = data.rolling(window=window).std()
    
    upper_band = middle_band + (std * num_std)
    lower_band = middle_band - (std * num_std)
    
    return upper_band, middle_band, lower_band

