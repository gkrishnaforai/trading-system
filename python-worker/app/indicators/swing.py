"""
Swing Trading Specific Indicators
ADX, Stochastic, Williams %R, VWAP, Fibonacci Retracements
Industry Standard: Technical analysis indicators for swing trading
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from app.exceptions import ValidationError


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Dict[str, pd.Series]:
    """
    Calculate Average Directional Index (ADX)
    
    ADX measures trend strength (0-100)
    - ADX > 25: Strong trend
    - ADX < 20: Weak trend or ranging market
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: Period for calculation (default: 14)
    
    Returns:
        Dictionary with 'adx', 'di_plus', 'di_minus'
    
    Raises:
        ValidationError: If inputs are invalid
    """
    if high is None or low is None or close is None:
        raise ValidationError("High, low, and close series are required")
    
    if len(high) < period or len(low) < period or len(close) < period:
        raise ValidationError(f"Insufficient data: need at least {period} periods")
    
    # Calculate True Range
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Calculate Directional Movement
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    # Only keep positive values
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    
    # If both move in same direction, set smaller to zero
    both_positive = (plus_dm > 0) & (minus_dm > 0)
    plus_dm[both_positive & (plus_dm < minus_dm)] = 0
    minus_dm[both_positive & (minus_dm < plus_dm)] = 0
    
    # Smooth TR and DM using Wilder's smoothing
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    
    # Calculate DX (Directional Index)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    dx = dx.replace([np.inf, -np.inf], np.nan)
    
    # Calculate ADX (smoothed DX)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return {
        'adx': adx,
        'di_plus': plus_di,
        'di_minus': minus_di
    }


def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3
) -> Dict[str, pd.Series]:
    """
    Calculate Stochastic Oscillator
    
    Stochastic measures momentum (0-100)
    - K > 80: Overbought
    - K < 20: Oversold
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        k_period: Period for %K calculation (default: 14)
        d_period: Period for %D smoothing (default: 3)
    
    Returns:
        Dictionary with 'stochastic_k', 'stochastic_d'
    
    Raises:
        ValidationError: If inputs are invalid
    """
    if high is None or low is None or close is None:
        raise ValidationError("High, low, and close series are required")
    
    if len(high) < k_period or len(low) < k_period or len(close) < k_period:
        raise ValidationError(f"Insufficient data: need at least {k_period} periods")
    
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    
    # Calculate %K
    k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
    k = k.replace([np.inf, -np.inf], np.nan)
    
    # Calculate %D (smoothed %K)
    d = k.rolling(d_period).mean()
    
    return {
        'stochastic_k': k,
        'stochastic_d': d
    }


def calculate_williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate Williams %R
    
    Williams %R measures momentum (-100 to 0)
    - %R > -20: Overbought
    - %R < -80: Oversold
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: Period for calculation (default: 14)
    
    Returns:
        Williams %R series
    
    Raises:
        ValidationError: If inputs are invalid
    """
    if high is None or low is None or close is None:
        raise ValidationError("High, low, and close series are required")
    
    if len(high) < period or len(low) < period or len(close) < period:
        raise ValidationError(f"Insufficient data: need at least {period} periods")
    
    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()
    
    wr = -100 * ((highest_high - close) / (highest_high - lowest_low))
    wr = wr.replace([np.inf, -np.inf], np.nan)
    
    return wr


def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    period: Optional[int] = None
) -> pd.Series:
    """
    Calculate Volume Weighted Average Price (VWAP)
    
    VWAP is the average price weighted by volume
    - Price above VWAP: Bullish
    - Price below VWAP: Bearish
    
    Args:
        high: High prices
        low: Low prices
        close: Close prices
        volume: Volume
        period: Period for rolling VWAP (None = cumulative)
    
    Returns:
        VWAP series
    
    Raises:
        ValidationError: If inputs are invalid
    """
    if high is None or low is None or close is None or volume is None:
        raise ValidationError("High, low, close, and volume series are required")
    
    if len(high) != len(low) or len(high) != len(close) or len(high) != len(volume):
        raise ValidationError("All series must have the same length")
    
    # Calculate typical price
    typical_price = (high + low + close) / 3
    
    # Calculate price * volume
    pv = typical_price * volume
    
    if period:
        if len(pv) < period:
            raise ValidationError(f"Insufficient data: need at least {period} periods")
        vwap = pv.rolling(period).sum() / volume.rolling(period).sum()
    else:
        vwap = pv.cumsum() / volume.cumsum()
    
    vwap = vwap.replace([np.inf, -np.inf], np.nan)
    
    return vwap


def calculate_fibonacci_retracements(
    high: pd.Series,
    low: pd.Series,
    period: int = 20
) -> Dict[str, pd.Series]:
    """
    Calculate Fibonacci Retracement Levels
    
    Fibonacci levels: 38.2%, 50%, 61.8%
    Used for support/resistance levels
    
    Args:
        high: High prices
        low: Low prices
        period: Period for swing high/low calculation (default: 20)
    
    Returns:
        Dictionary with 'fib_382', 'fib_500', 'fib_618'
    
    Raises:
        ValidationError: If inputs are invalid
    """
    if high is None or low is None:
        raise ValidationError("High and low series are required")
    
    if len(high) < period or len(low) < period:
        raise ValidationError(f"Insufficient data: need at least {period} periods")
    
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    diff = highest - lowest
    
    # Calculate Fibonacci levels
    fib_382 = highest - (diff * 0.382)
    fib_500 = highest - (diff * 0.500)
    fib_618 = highest - (diff * 0.618)
    
    return {
        'fib_382': fib_382,
        'fib_500': fib_500,
        'fib_618': fib_618
    }

