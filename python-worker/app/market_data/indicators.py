"""
Quant helpers on canonical bars — thin adapter over app.indicators so
the quant layer's numbers match what backtests and indicator_service
already produce (single source of truth for indicator math).

All functions accept List[OHLCVBar] and return scalars or pd.Series.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import pandas as pd

from app.indicators.momentum import calculate_rsi, calculate_macd
from app.indicators.moving_averages import calculate_ema, calculate_sma
from app.indicators.volatility import calculate_atr

from .models import OHLCVBar


# ---------- series plumbing ----------

def closes(bars: List[OHLCVBar], adjusted: bool = True) -> pd.Series:
    """Close series indexed by bar timestamp; adj_close when present."""
    if adjusted:
        vals = [b.adj_close or b.close for b in bars]
    else:
        vals = [b.close for b in bars]
    return pd.Series(vals, index=[b.timestamp for b in bars], dtype=float)


def _ohlc_series(bars: List[OHLCVBar]) -> Tuple[pd.Series, pd.Series, pd.Series]:
    idx = [b.timestamp for b in bars]
    return (
        pd.Series([b.high for b in bars], index=idx, dtype=float),
        pd.Series([b.low for b in bars], index=idx, dtype=float),
        pd.Series([b.close for b in bars], index=idx, dtype=float),
    )


def _last(s: pd.Series, offset: int = 0) -> Optional[float]:
    """Scalar at position -(1+offset); None if NaN or out of range."""
    i = len(s) - 1 - offset
    if i < 0:
        return None
    v = s.iloc[i]
    return None if pd.isna(v) else float(v)


def _ret(s: pd.Series, periods: int) -> Optional[float]:
    if len(s) < periods + 1:
        return None
    prev = s.iloc[-1 - periods]
    return float(s.iloc[-1] / prev - 1) if prev else None


# ---------- moving averages ----------

def sma_series(bars: List[OHLCVBar], window: int) -> pd.Series:
    return calculate_sma(closes(bars), window)


def sma(bars: List[OHLCVBar], window: int) -> Optional[float]:
    return _last(sma_series(bars, window))


def ema_series(bars: List[OHLCVBar], window: int) -> pd.Series:
    return calculate_ema(closes(bars), window)


def ema(bars: List[OHLCVBar], window: int) -> Optional[float]:
    return _last(ema_series(bars, window))


def sma_slope(bars: List[OHLCVBar], window: int, lookback: int = 5) -> Optional[float]:
    """Annualized-free slope: (MA_now - MA_lookback)/lookback, % per day."""
    s = sma_series(bars, window).dropna()
    if len(s) < lookback + 1:
        return None
    prev = s.iloc[-1 - lookback]
    return float((s.iloc[-1] - prev) / lookback / prev) if prev else None


def pct_from_sma(bars: List[OHLCVBar], window: int) -> Optional[float]:
    s = _last(sma_series(bars, window))
    c = closes(bars)
    if s is None or len(c) == 0:
        return None
    return float(c.iloc[-1] / s - 1)


# ---------- momentum ----------

def rsi_series(bars: List[OHLCVBar], period: int = 14) -> pd.Series:
    return calculate_rsi(closes(bars), window=period)


def rsi(bars: List[OHLCVBar], period: int = 14, offset: int = 0) -> Optional[float]:
    return _last(rsi_series(bars, period), offset)


def macd(bars: List[OHLCVBar]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(macd_line, signal, histogram) latest values."""
    line, sig, hist = calculate_macd(closes(bars))
    return _last(line), _last(sig), _last(hist)


def roc(bars: List[OHLCVBar], periods: int) -> Optional[float]:
    """Rate of change over `periods` bars."""
    return _ret(closes(bars), periods)


def returns(bars: List[OHLCVBar], periods: int) -> Optional[float]:
    """Simple total return over `periods` bars (same as roc on closes)."""
    return _ret(closes(bars), periods)


# ---------- volatility ----------

def atr(bars: List[OHLCVBar], window: int = 14) -> Optional[float]:
    h, l, c = _ohlc_series(bars)
    return _last(calculate_atr(h, l, c, window))


def atr_pct(bars: List[OHLCVBar], window: int = 14) -> Optional[float]:
    a = atr(bars, window)
    c = closes(bars)
    if a is None or len(c) == 0 or not c.iloc[-1]:
        return None
    return a / c.iloc[-1]


def realized_vol(bars: List[OHLCVBar], window: int = 20,
                 offset: int = 0) -> Optional[float]:
    """Annualized stdev of daily log returns over `window` ending at -offset."""
    c = closes(bars)
    end = len(c) - offset
    if end - window - 1 < 0 or end <= 0:
        return None
    rets = c.pct_change().iloc[max(1, end - window - 1):end].dropna()
    if len(rets) < window * 0.8:
        return None
    return float(rets.std() * math.sqrt(252))


def percentile_rank(series: pd.Series, window: int = 20) -> Optional[float]:
    """Percentile of the latest value within trailing `window` values (0-100)."""
    s = series.dropna().iloc[-window:]
    if len(s) < 5:
        return None
    return float((s <= s.iloc[-1]).mean() * 100)


# ---------- volume / structure ----------

def volume_ratio(bars: List[OHLCVBar], window: int = 20,
                 offset: int = 0) -> Optional[float]:
    """Bar volume at -offset / average volume over `window` before it."""
    vols = [b.volume for b in bars if b.volume is not None]
    end = len(vols) - offset
    if end < window + 1:
        return None
    avg = sum(vols[end - window - 1:end - 1]) / window
    return vols[end - 1] / avg if avg else None


def drawdown_from_high(bars: List[OHLCVBar], window: Optional[int] = None) -> Optional[float]:
    """Latest close vs max high over `window` bars (all bars if None)."""
    if not bars:
        return None
    sub = bars[-window:] if window else bars
    hi = max(b.high for b in sub)
    c = closes(bars)
    if not hi or len(c) == 0:
        return None
    return float(c.iloc[-1] / hi - 1)


def swing_structure(bars: List[OHLCVBar], window: int = 20) -> Tuple[bool, bool]:
    """(higher_high, higher_low): recent `window` extremes vs the prior window."""
    if len(bars) < window * 2:
        return False, False
    recent, prior = bars[-window:], bars[-window * 2:-window]
    hh = max(b.high for b in recent) > max(b.high for b in prior)
    hl = min(b.low for b in recent) > min(b.low for b in prior)
    return hh, hl


def dist_from_extreme(bars: List[OHLCVBar], window: int = 20,
                      high: bool = True) -> Optional[float]:
    if not bars:
        return None
    sub = bars[-window:]
    c = closes(bars)
    if len(c) == 0:
        return None
    ext = max(b.high for b in sub) if high else min(b.low for b in sub)
    return float(c.iloc[-1] / ext - 1) if ext else None
