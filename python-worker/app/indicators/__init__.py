"""
Technical indicators module
All indicator calculations follow DRY and SOLID principles
"""

from app.indicators.moving_averages import (
    calculate_sma,
    calculate_ema,
    calculate_ma7,
    calculate_ma21,
    calculate_sma50,
    calculate_ema20,
    calculate_ema50,
    calculate_sma200
)

from app.indicators.momentum import (
    calculate_rsi,
    calculate_macd,
    calculate_momentum_score
)

from app.indicators.volatility import (
    calculate_atr,
    calculate_bollinger_bands
)

from app.indicators.trend import (
    detect_long_term_trend,
    detect_medium_term_trend
)

from app.indicators.swing import (
    calculate_adx,
    calculate_stochastic,
    calculate_williams_r,
    calculate_vwap,
    calculate_fibonacci_retracements
)

__all__ = [
    # Moving Averages
    "calculate_sma",
    "calculate_ema",
    "calculate_ma7",
    "calculate_ma21",
    "calculate_sma50",
    "calculate_ema20",
    "calculate_ema50",
    "calculate_sma200",
    # Momentum
    "calculate_rsi",
    "calculate_macd",
    "calculate_momentum_score",
    # Volatility
    "calculate_atr",
    "calculate_bollinger_bands",
    # Trend
    "detect_long_term_trend",
    "detect_medium_term_trend",
    # Swing Trading
    "calculate_adx",
    "calculate_stochastic",
    "calculate_williams_r",
    "calculate_vwap",
    "calculate_fibonacci_retracements",
]

