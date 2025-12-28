"""
Moving Average calculations
"""
import logging
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def calculate_sma(data: pd.Series, window: int) -> pd.Series:
    """
    Calculate Simple Moving Average
    
    Args:
        data: Price series (typically close prices)
        window: Number of periods
    
    Returns:
        Series with SMA values
    """
    if len(data) < window:
        logger.warning(f"Insufficient data for SMA{window}: {len(data)} < {window}")
        return pd.Series([np.nan] * len(data), index=data.index)
    
    return data.rolling(window=window).mean()


def calculate_ema(data: pd.Series, window: int, alpha: Optional[float] = None) -> pd.Series:
    """
    Calculate Exponential Moving Average
    
    Industry Standard: EMA calculation with proper NaN handling
    - Drops leading NaNs from input
    - Calculates EMA on valid data
    - Returns series with same index as input (NaNs preserved where input was NaN)
    
    Args:
        data: Price series (typically close prices)
        window: Number of periods
        alpha: Smoothing factor (optional, calculated from window if not provided)
    
    Returns:
        Series with EMA values
    """
    if len(data) < window:
        logger.warning(f"Insufficient data for EMA{window}: {len(data)} < {window}")
        return pd.Series([np.nan] * len(data), index=data.index)
    
    # Check for NaN values - if all are NaN, return all NaN
    valid_data = data.dropna()
    if len(valid_data) < window:
        logger.warning(f"Insufficient valid data for EMA{window}: {len(valid_data)} valid values < {window}")
        return pd.Series([np.nan] * len(data), index=data.index)
    
    # If data has NaNs, we need to handle them carefully
    # EMA calculation: forward fill NaNs first, then calculate EMA
    # This is industry standard - use last known value for missing periods
    # Use ffill() and bfill() instead of deprecated fillna(method=...)
    data_filled = data.ffill().bfill()
    
    # If still all NaN after fill, return all NaN
    if data_filled.isna().all():
        logger.warning(f"All NaN values in data for EMA{window} calculation")
        return pd.Series([np.nan] * len(data), index=data.index)
    
    # Calculate EMA
    ema_result = data_filled.ewm(span=window, adjust=False).mean()
    
    # Restore original NaNs where input was NaN (preserve data gaps)
    # Only restore if original had NaN and we have enough valid data
    if data.isna().any():
        # Keep EMA values where we had valid input, NaN where input was NaN
        ema_result = ema_result.where(data.notna(), np.nan)
    
    return ema_result


# Convenience functions for specific moving averages
def calculate_ma7(data: pd.Series) -> pd.Series:
    """Calculate 7-day moving average"""
    return calculate_sma(data, 7)


def calculate_ma21(data: pd.Series) -> pd.Series:
    """Calculate 21-day moving average"""
    return calculate_sma(data, 21)


def calculate_sma50(data: pd.Series) -> pd.Series:
    """Calculate 50-day Simple Moving Average"""
    return calculate_sma(data, 50)


def calculate_ema20(data: pd.Series) -> pd.Series:
    """Calculate 20-day Exponential Moving Average"""
    return calculate_ema(data, 20)


def calculate_ema50(data: pd.Series) -> pd.Series:
    """Calculate 50-day Exponential Moving Average"""
    return calculate_ema(data, 50)


def calculate_sma200(data: pd.Series) -> pd.Series:
    """Calculate 200-day Simple Moving Average"""
    return calculate_sma(data, 200)

