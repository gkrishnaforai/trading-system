import numpy as np
import pandas as pd

from app.indicators.moving_averages import calculate_sma, calculate_ema
from app.indicators.momentum import calculate_rsi, calculate_macd
from app.indicators.volatility import calculate_atr


def _series(values) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2020-01-01", periods=len(values), freq="D"))


def test_sma_insufficient_data_returns_all_nan() -> None:
    s = _series([1, 2, 3, 4])
    out = calculate_sma(s, window=10)
    assert len(out) == len(s)
    assert out.isna().all()


def test_ema_insufficient_data_returns_all_nan() -> None:
    s = _series([1, 2, 3, 4])
    out = calculate_ema(s, window=10)
    assert len(out) == len(s)
    assert out.isna().all()


def test_ema_preserves_nan_gaps() -> None:
    # Our EMA implementation ffill/bfill for computation but restores NaNs where input was NaN.
    s = _series([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0])
    out = calculate_ema(s, window=5)

    assert len(out) == len(s)
    assert np.isnan(out.iloc[2])  # the NaN gap is preserved
    assert np.isfinite(out.dropna()).all()


def test_rsi_constant_series_is_neutral_50() -> None:
    # For a constant series, avg_loss tends to 0; our RSI implementation returns neutral 50.
    s = _series([100.0] * 60)
    out = calculate_rsi(s, window=14)

    assert len(out) == len(s)
    last = float(out.iloc[-1])
    assert 49.0 <= last <= 51.0


def test_rsi_insufficient_data_returns_length_preserving_series() -> None:
    s = _series([1.0] * 5)
    out = calculate_rsi(s, window=14)
    assert len(out) == len(s)


def test_macd_insufficient_data_returns_all_nan_series() -> None:
    s = _series([1.0] * 10)
    macd_line, signal, hist = calculate_macd(s, fast_period=12, slow_period=26, signal_period=9)

    assert len(macd_line) == len(s)
    assert len(signal) == len(s)
    assert len(hist) == len(s)
    assert macd_line.isna().all()
    assert signal.isna().all()
    assert hist.isna().all()


def test_macd_shapes_and_finiteness_on_valid_data() -> None:
    # Increasing series should yield finite MACD values at the end.
    s = _series(np.linspace(1.0, 200.0, 200))
    macd_line, signal, hist = calculate_macd(s, fast_period=12, slow_period=26, signal_period=9)

    assert len(macd_line) == len(s)
    assert len(signal) == len(s)
    assert len(hist) == len(s)

    assert np.isfinite(float(macd_line.iloc[-1]))
    assert np.isfinite(float(signal.iloc[-1]))
    assert np.isfinite(float(hist.iloc[-1]))


def test_atr_constant_prices_is_zero_after_warmup() -> None:
    # If high=low=close each day, true range is 0, so ATR should trend to 0.
    n = 50
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    high = pd.Series([10.0] * n, index=idx)
    low = pd.Series([10.0] * n, index=idx)
    close = pd.Series([10.0] * n, index=idx)

    atr = calculate_atr(high, low, close, window=14)
    assert len(atr) == n

    # After warmup, ATR should be very close to 0
    tail = atr.dropna().tail(5)
    assert (tail.abs() < 1e-9).all()
