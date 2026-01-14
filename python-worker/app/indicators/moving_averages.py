"""
Moving Average calculations (Industry Standard)

- No forward-fill or backward-fill
- No lookahead bias
- Matches TradingView EMA/SMA behavior
"""

import logging
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


# =========================
# Simple Moving Average
# =========================
def calculate_sma(data: pd.Series, window: int) -> pd.Series:
    """
    Calculate Simple Moving Average (SMA)

    Args:
        data: Price series (close prices)
        window: Number of periods

    Returns:
        SMA series
    """
    if len(data) < window:
        logger.warning(f"Insufficient data for SMA{window}: {len(data)} < {window}")
        return pd.Series(np.nan, index=data.index)

    return data.rolling(
        window=window,
        min_periods=window
    ).mean()


# =========================
# Exponential Moving Average
# =========================
def calculate_ema(
    data: pd.Series,
    window: int,
    alpha: Optional[float] = None
) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA)

    Industry-standard implementation:
    - No forward-fill
    - No backward-fill
    - No NaN restoration
    - No lookahead bias
    - EMA starts only after enough data

    Args:
        data: Price series (close prices)
        window: Number of periods
        alpha: Optional smoothing factor (overrides span)

    Returns:
        EMA series
    """
    if len(data) < window:
        logger.warning(f"Insufficient data for EMA{window}: {len(data)} < {window}")
        return pd.Series(np.nan, index=data.index)

    ewm_kwargs = {
        "adjust": False,
        "min_periods": window
    }

    if alpha is not None:
        ewm_kwargs["alpha"] = alpha
    else:
        ewm_kwargs["span"] = window

    return data.ewm(**ewm_kwargs).mean()


# =========================
# Convenience Wrappers
# =========================
def calculate_ma7(data: pd.Series) -> pd.Series:
    """7-period SMA"""
    return calculate_sma(data, 7)


def calculate_ma21(data: pd.Series) -> pd.Series:
    """21-period SMA"""
    return calculate_sma(data, 21)


def calculate_sma50(data: pd.Series) -> pd.Series:
    """50-period SMA"""
    return calculate_sma(data, 50)


def calculate_ema20(data: pd.Series) -> pd.Series:
    """20-period EMA"""
    return calculate_ema(data, 20)


def calculate_ema50(data: pd.Series) -> pd.Series:
    """50-period EMA"""
    return calculate_ema(data, 50)


def calculate_sma200(data: pd.Series) -> pd.Series:
    """200-period SMA"""
    return calculate_sma(data, 200)
