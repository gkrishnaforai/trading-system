"""Canonical daily-bars data layer — fetch once, use everywhere.

One module owns yfinance bar ingestion for the whole system:

    refresh(symbols, period)  batched yf.download → upsert daily_bars
                              → returns {sym: [Bar-like namespaces]}
    load(symbols, days)       read daily_bars → same shape
    live(symbol, period)      on-demand single-symbol fetch, no table

Consumers (momentum, priors, pilot) never call yf.download directly —
they call refresh (writer job) or load (readers). This is the DRY fix
for the repeated per-job downloads.
"""
from __future__ import annotations

import logging
from datetime import date
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

_MIN_STORED = 200          # below this a symbol needs a live top-up
_YF_TIMEOUT = 20           # seconds per yf request — a hung Yahoo
                           # socket must not stall a whole job


def _fetchable(symbol: str) -> bool:
    """Symbols yfinance can't serve — numeric junk, warrants/units/
    preferreds in Yahoo notation — fail slow; skip them up front."""
    import re
    if not symbol or symbol.isdigit():
        return False
    return not re.search(r"-(WT|UN|PA|PB|PC|PD|PE|PF|WS|RT|U)$",
                         symbol)


def _frame_to_bars(frame) -> list[SimpleNamespace]:
    """Normalize one symbol's OHLCV dataframe → namespace bars."""
    import pandas as pd
    d = frame.dropna(subset=["Close"])
    return [SimpleNamespace(
        timestamp=i.to_pydatetime(), date=i.date(),
        open=float(r.Open), high=float(r.High),
        low=float(r.Low), close=float(r.Close),
        adj_close=None,
        volume=float(r.Volume) if pd.notna(r.Volume) else 0)
        for i, r in d.iterrows()]


def _upsert(sym: str, bars: list[SimpleNamespace]):
    from app.database import db
    db.execute_many(
        "INSERT INTO daily_bars (symbol, date, open, high, low, close,"
        " volume) VALUES (:s,:d,:o,:h,:l,:c,:v)"
        " ON CONFLICT (symbol, date) DO UPDATE SET"
        " open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,"
        " close=EXCLUDED.close, volume=EXCLUDED.volume",
        [{"s": sym, "d": b.date, "o": b.open, "h": b.high,
          "l": b.low, "c": b.close, "v": int(b.volume or 0)}
         for b in bars])


def refresh(symbols: list[str], period: str = "2y") -> dict[str, Any]:
    """The daily technicals fetch — batched download + store. Returns
    the bars so the caller can classify from memory without re-read."""
    import yfinance as yf
    from app.database import db
    if not symbols:
        return {}
    px = yf.download(" ".join(symbols), period=period, interval="1d",
                     group_by="ticker", threads=True, progress=False,
                     auto_adjust=True, timeout=_YF_TIMEOUT)
    out: dict[str, list] = {}
    for s in symbols:
        try:
            try:
                sub = px[s]
            except (KeyError, TypeError):
                sub = px
            bars = _frame_to_bars(sub)
            if not bars:
                continue
            out[s] = bars
            try:
                _upsert(s, bars)
            except Exception as exc:
                logger.debug("bars upsert %s: %s", s, exc)
        except Exception as exc:
            logger.debug("bars fetch %s: %s", s, exc)
    return out


def load(symbols: list[str], days: int = 500) -> dict[str, Any]:
    """Read canonical bars — the shared path for every consumer.
    Symbols with thin/no stored history get a live top-up once."""
    from app.database import db
    if not symbols:
        return {}
    rows = db.execute_query(
        "SELECT symbol, date, open, high, low, close, volume"
        " FROM (SELECT *, row_number() OVER (PARTITION BY symbol"
        "        ORDER BY date DESC) rn FROM daily_bars"
        "       WHERE symbol = ANY(:syms)) t WHERE rn <= :days"
        " ORDER BY symbol, date",
        {"syms": list(symbols), "days": days})
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["symbol"], []).append(SimpleNamespace(
            timestamp=None, date=r["date"],
            open=float(r["open"]), high=float(r["high"]),
            low=float(r["low"]), close=float(r["close"]),
            adj_close=None, volume=float(r["volume"] or 0)))
    thin = [s for s in symbols
            if len(out.get(s) or []) < _MIN_STORED and _fetchable(s)]
    if thin:
        # ONE batched top-up for all thin symbols — the old path called
        # live() per symbol, and a single delisted ticker could stall
        # the whole job through serial retries
        try:
            batch = refresh(thin, period="2y")
            for s, live_bars in batch.items():
                out[s] = live_bars[-days:]
        except Exception as exc:
            logger.debug("bars batch top-up: %s", exc)
    return out


def live(symbol: str, period: str = "2y") -> list[SimpleNamespace]:
    """On-demand single-symbol fetch — bypasses the table (user-driven
    lookups want the freshest possible bar)."""
    import yfinance as yf
    px = yf.download(symbol, period=period, interval="1d",
                     progress=False, auto_adjust=True,
                     timeout=_YF_TIMEOUT)
    if px is None or len(px) == 0:
        return []
    if hasattr(px.columns, "levels"):        # flatten any MultiIndex
        px.columns = [c[0] if isinstance(c, tuple) else c
                      for c in px.columns]
    return _frame_to_bars(px)


def coverage() -> dict[str, Any]:
    """Health read for the board/registry — rows + staleness."""
    from app.database import db
    r = db.execute_query(
        "SELECT count(DISTINCT symbol) syms, count(*) rows,"
        " max(date) latest FROM daily_bars")[0]
    return r


def as_dataframe(bars: list[SimpleNamespace]):
    """Namespace bars → OHLCV dataframe (classifier input shape)."""
    import pandas as pd
    return pd.DataFrame(
        {"Open": b.open, "High": b.high, "Low": b.low,
         "Close": b.close, "Volume": b.volume}
        for b in bars)
