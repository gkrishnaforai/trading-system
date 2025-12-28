import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from app.providers.yahoo_finance.client import YahooFinanceClient
from app.indicators.moving_averages import calculate_sma, calculate_ema
from app.indicators.momentum import calculate_rsi, calculate_macd


@dataclass(frozen=True)
class IndicatorSnapshot:
    sma50: float
    ema20: float
    rsi14: float
    macd: float
    macd_signal: float
    macd_hist: float


def _last_finite(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce")
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        raise AssertionError("Series has no finite values")
    return float(s.iloc[-1])


def _assert_close(name: str, actual: float, expected: float, atol: float, rtol: float = 1e-6) -> None:
    if not np.isfinite(actual) or not np.isfinite(expected):
        raise AssertionError(f"Non-finite values for {name}: actual={actual}, expected={expected}")
    if not np.isclose(actual, expected, atol=atol, rtol=rtol):
        raise AssertionError(f"{name} mismatch: actual={actual}, expected={expected}, atol={atol}, rtol={rtol}")


@pytest.mark.integration
def test_aapl_indicators_match_talib_real_data() -> None:
    """
    Real-data validation test (no mocks):

    - Fetches AAPL daily OHLCV via Yahoo Finance (yfinance) through our YahooFinanceClient.
    - Computes indicators using our internal implementation.
    - Computes the same indicators using TA-Lib (industry standard) as an independent reference.

    This test is opt-in to avoid flaky CI failures due to rate limits / upstream 404s.

    Enable with:
      RUN_REAL_API_TESTS=1 pytest -k aapl_indicators_match_talib_real_data
    """

    if os.getenv("RUN_REAL_API_TESTS") != "1":
        pytest.skip("Set RUN_REAL_API_TESTS=1 to enable real API indicator validation")

    try:
        import talib  # type: ignore
    except Exception:
        pytest.skip("TA-Lib is not available in this environment")

    client = YahooFinanceClient.from_settings()

    # Use a longer window to ensure indicators stabilize (RSI, MACD).
    df = client.fetch_price_data("AAPL", days=365)

    assert isinstance(df, pd.DataFrame)
    assert not df.empty

    # Normalize column names to what our indicator functions expect.
    close = df["close"].astype(float)

    # Our calculations
    our_sma50 = calculate_sma(close, 50)
    our_ema20 = calculate_ema(close, 20)
    our_rsi14 = calculate_rsi(close, 14)
    our_macd, our_macd_signal, our_macd_hist = calculate_macd(close, 12, 26, 9)

    our = IndicatorSnapshot(
        sma50=_last_finite(our_sma50),
        ema20=_last_finite(our_ema20),
        rsi14=_last_finite(our_rsi14),
        macd=_last_finite(our_macd),
        macd_signal=_last_finite(our_macd_signal),
        macd_hist=_last_finite(our_macd_hist),
    )

    # TA-Lib reference calculations
    close_np = close.to_numpy(dtype=float)

    ref_sma50 = talib.SMA(close_np, timeperiod=50)
    ref_ema20 = talib.EMA(close_np, timeperiod=20)
    ref_rsi14 = talib.RSI(close_np, timeperiod=14)
    ref_macd, ref_macd_signal, ref_macd_hist = talib.MACD(
        close_np, fastperiod=12, slowperiod=26, signalperiod=9
    )

    ref = IndicatorSnapshot(
        sma50=float(pd.Series(ref_sma50).replace([np.inf, -np.inf], np.nan).dropna().iloc[-1]),
        ema20=float(pd.Series(ref_ema20).replace([np.inf, -np.inf], np.nan).dropna().iloc[-1]),
        rsi14=float(pd.Series(ref_rsi14).replace([np.inf, -np.inf], np.nan).dropna().iloc[-1]),
        macd=float(pd.Series(ref_macd).replace([np.inf, -np.inf], np.nan).dropna().iloc[-1]),
        macd_signal=float(pd.Series(ref_macd_signal).replace([np.inf, -np.inf], np.nan).dropna().iloc[-1]),
        macd_hist=float(pd.Series(ref_macd_hist).replace([np.inf, -np.inf], np.nan).dropna().iloc[-1]),
    )

    # Tolerances: floating differences are expected due to initialization/smoothing nuances.
    # These are intentionally tight enough to catch logic regressions.
    _assert_close("SMA50", our.sma50, ref.sma50, atol=1e-6)
    _assert_close("EMA20", our.ema20, ref.ema20, atol=1e-6)

    # RSI can differ slightly depending on warmup handling; allow a small tolerance.
    _assert_close("RSI14", our.rsi14, ref.rsi14, atol=0.25)

    # MACD family: allow small tolerance.
    _assert_close("MACD", our.macd, ref.macd, atol=1e-4)
    _assert_close("MACD_SIGNAL", our.macd_signal, ref.macd_signal, atol=1e-4)
    _assert_close("MACD_HIST", our.macd_hist, ref.macd_hist, atol=1e-4)
