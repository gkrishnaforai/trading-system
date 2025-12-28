"""
Trend detection indicators
"""
import logging
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def detect_long_term_trend(
    price: pd.Series,
    sma200: pd.Series
) -> pd.Series:
    """
    Detect long-term trend based on price vs 200-day SMA
    
    Returns:
        Series with 'bullish', 'bearish', or 'neutral'
    """
    if len(price) != len(sma200):
        logger.warning("Price and SMA200 series length mismatch")
        return pd.Series(['neutral'] * len(price), index=price.index)
    
    trend = pd.Series('neutral', index=price.index)
    
    # Bullish: price > SMA200
    trend[price > sma200] = 'bullish'
    # Bearish: price < SMA200
    trend[price < sma200] = 'bearish'
    
    return trend


def detect_medium_term_trend(
    ema20: pd.Series,
    sma50: pd.Series
) -> pd.Series:
    """
    Detect medium-term trend based on EMA20 vs SMA50
    
    Returns:
        Series with 'bullish', 'bearish', or 'neutral'
    """
    if len(ema20) != len(sma50):
        logger.warning("EMA20 and SMA50 series length mismatch")
        return pd.Series(['neutral'] * len(ema20), index=ema20.index)
    
    trend = pd.Series('neutral', index=ema20.index)
    
    # Bullish: EMA20 > SMA50
    trend[ema20 > sma50] = 'bullish'
    # Bearish: EMA20 < SMA50
    trend[ema20 < sma50] = 'bearish'
    
    return trend

