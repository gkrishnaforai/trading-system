"""Pre-market session snapshot — the gap + overnight-crypto read that
journaled tape leaves dark between yesterday's close and the first
RTH eval.

Runs twice per session (job fires ~8:25 and ~9:25 ET): the 'early'
and 'final' slots let the card show whether the gap firmed or faded
into the open — a gap that decays through pre-market is weaker
evidence than one that holds.

Equity legs come from yfinance extended-hours bars (prepost=True);
crypto legs are 24h changes — BTC/ETH trade through the night, so
they're the only risk-sentiment gauge live while equities sleep.

Once enough (date, slot, gap → day_ret) history accrues, the gaps
join base_rates as a conditioning leg — journaled first, measured
against outcomes, never asserted.
"""

import json
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def _slot(now_et: datetime) -> str:
    return "early" if now_et.hour < 9 else "final"


def _pm_last(sym: str) -> Optional[float]:
    """Most recent extended-hours price for an equity ETF."""
    import yfinance as yf
    df = yf.download(sym, period="2d", interval="5m",
                     prepost=True, progress=False, timeout=30)
    if df is None or df.empty:
        return None
    closes = df["Close"]
    if hasattr(closes, "columns"):          # MultiIndex (sym,) shape
        closes = closes.iloc[:, 0]
    v = closes.dropna().iloc[-1]
    return float(v)


def _crypto_24h(sym: str) -> Optional[float]:
    """24h change for a 24/7 asset — the overnight risk-sentiment leg."""
    import yfinance as yf
    df = yf.download(sym, period="2d", interval="1h",
                     progress=False, timeout=30)
    if df is None or len(df) < 20:
        return None
    closes = df["Close"]
    if hasattr(closes, "columns"):
        closes = closes.iloc[:, 0]
    c = closes.dropna()
    if len(c) < 20:
        return None
    now_p, prev_p = float(c.iloc[-1]), float(c.iloc[-24])
    return now_p / prev_p - 1 if prev_p else None


def snapshot(persist: bool = True) -> dict[str, Any]:
    """Journal one pre-market row for today's slot."""
    from app.database import db
    now_et = datetime.now(_ET)
    slot = _slot(now_et)

    prior: dict[str, Optional[float]] = {}
    for s in ("SPY", "QQQ", "SMH"):
        r = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " ORDER BY date DESC LIMIT 1", {"s": s})
        prior[s] = float(r[0]["close"]) if r else None

    legs: dict[str, dict] = {}
    for s in ("SPY", "QQQ", "SMH"):
        pm = None
        try:
            pm = _pm_last(s)
        except Exception:
            pass
        gap = (pm / prior[s] - 1) if (pm and prior[s]) else None
        legs[s] = {"pm": pm, "gap": gap}

    crypto: dict[str, Optional[float]] = {}
    for s in ("BTC-USD", "ETH-USD"):
        try:
            crypto[s] = _crypto_24h(s)
        except Exception:
            crypto[s] = None

    out = {"date": now_et.date().isoformat(), "slot": slot,
           "ts": now_et.isoformat(), "legs": legs, "crypto": crypto}
    if persist:
        db.execute_update(
            "INSERT INTO premarket_snapshots"
            " (date, slot, ts, qqq_pm, qqq_gap, spy_pm, spy_gap,"
            "  smh_pm, smh_gap, btc_chg, eth_chg, raw)"
            " VALUES (:d,:sl,now(),:qqp,:qqg,:spp,:spg,:smp,:smg,"
            "         :bc,:ec,:raw)"
            " ON CONFLICT (date, slot) DO UPDATE SET"
            " ts=now(), qqq_pm=:qqp, qqq_gap=:qqg, spy_pm=:spp,"
            " spy_gap=:spg, smh_pm=:smp, smh_gap=:smg,"
            " btc_chg=:bc, eth_chg=:ec, raw=:raw",
            {"d": out["date"], "sl": slot,
             "qqp": legs["QQQ"]["pm"], "qqg": legs["QQQ"]["gap"],
             "spp": legs["SPY"]["pm"], "spg": legs["SPY"]["gap"],
             "smp": legs["SMH"]["pm"], "smg": legs["SMH"]["gap"],
             "bc": crypto["BTC-USD"], "ec": crypto["ETH-USD"],
             "raw": json.dumps(out, default=str)})
    return out


def latest(date: str | None = None) -> list[dict]:
    """Journaled slots for a date (default today) — early→final gap
    drift is the firming/fading read the card renders."""
    from app.database import db
    if date:
        return db.execute_query(
            "SELECT * FROM premarket_snapshots WHERE date=:d"
            " ORDER BY slot", {"d": date})
    return db.execute_query(
        "SELECT * FROM premarket_snapshots WHERE date=CURRENT_DATE"
        " ORDER BY slot")
