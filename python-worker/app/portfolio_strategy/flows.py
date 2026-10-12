"""Real ETF fund flows — derived from AUM snapshots.

flow(d) ≈ AUM(d) − AUM(d−1) × (1 + ret(d))

The share of an ETF's AUM change not explained by market movement is
net creations/redemptions — that's what fund-flow data actually IS.
We snapshot AUM daily via FMP /stable/etf/info; after ~10 trading
days the flow series becomes usable, after ~60 it's trustworthy.

Falls back to the signed-volume proxy until history exists — the
`flow_source` field marks which engine produced the number.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_BASE = "https://financialmodelingprep.com/stable"


def snapshot_aum(symbols: list[str]) -> int:
    """Pull today's AUM+NAV per ETF → etf_aum_snapshots. Returns count
    written. Runs daily — ~20 calls, well inside the FMP quota."""
    from app.database import db
    key = os.getenv("FMP_API_KEY") or os.getenv("FMP_KEY")
    if not key:
        return 0
    today = date.today().isoformat()
    n = 0
    for sym in symbols:
        try:
            r = requests.get(f"{_BASE}/etf/info",
                             params={"symbol": sym, "apikey": key},
                             timeout=15)
            rows = r.json()
            if not rows:
                continue
            aum = rows[0].get("assetsUnderManagement")
            nav = rows[0].get("nav")
            if not aum:
                continue
            db.execute_update(
                "INSERT INTO etf_aum_snapshots "
                "(snap_date, symbol, aum, nav, shares) "
                "VALUES (:d, :s, :a, :n, :sh) "
                "ON CONFLICT (snap_date, symbol) DO UPDATE SET "
                "aum=:a, nav=:n, shares=:sh",
                {"d": today, "s": sym, "a": float(aum),
                 "n": float(nav) if nav else None,
                 "sh": (float(aum) / float(nav)) if nav else None})
            n += 1
        except Exception as exc:
            logger.debug("aum snapshot %s: %s", sym, exc)
    return n


def fund_flows(symbols: list[str], lookback: int = 20) -> dict[str, dict]:
    """Derive per-ETF flow series. Returns {sym: {flow_5d, flow_20d,
    flow_pct, source, days}} — flow_* are $, flow_pct is % of AUM.
    `source` = 'aum' when real history exists, 'volume' when only the
    price×volume proxy is available (flow fields then None)."""
    from app.database import db
    from app.market_data import bars as bars_mod
    out = {}
    books = bars_mod.load(symbols, days=lookback + 30)
    for sym in symbols:
        try:
            snaps = db.execute_query(
                "SELECT snap_date, aum, nav FROM etf_aum_snapshots "
                "WHERE symbol=:s ORDER BY snap_date DESC LIMIT :n",
                {"s": sym, "n": lookback + 5})
        except Exception:
            snaps = []
        if len(snaps) < 5:
            out[sym] = {"source": "volume", "days": len(snaps),
                        "flow_5d": None, "flow_20d": None,
                        "flow_pct": None}
            continue
        # build date→close map from bars for the return adjustment
        cls = {b.timestamp.date(): b.close for b in books.get(sym) or []}
        snaps = sorted(snaps, key=lambda r: r["snap_date"])
        flows = []                     # (date, $flow)
        for i in range(1, len(snaps)):
            d0, a0 = snaps[i - 1]["snap_date"], float(snaps[i - 1]["aum"])
            d1, a1 = snaps[i]["snap_date"], float(snaps[i]["aum"])
            c0, c1 = cls.get(d0), cls.get(d1)
            if c0 and c1 and a0:
                mkt = a0 * (c1 / c0 - 1)          # market-explained Δ
                flows.append((d1, a1 - a0 - mkt)) # residual = flow
        f5 = sum(f for _, f in flows[-5:])
        f20 = sum(f for _, f in flows[-20:])
        latest_aum = float(snaps[-1]["aum"]) or 1.0
        out[sym] = {"source": "aum", "days": len(snaps),
                    "flow_5d": round(f5), "flow_20d": round(f20),
                    "flow_pct": round(f20 / latest_aum * 100, 3)}
    return out


def refresh_flows() -> dict[str, Any]:
    """Daily job entry — snapshot today's AUM for the rotation
    universe, then return the derived flow table."""
    from app.market_regime.rotation import SECTOR_NAMES, THEME_ETFS
    syms = sorted(set(list(SECTOR_NAMES) + list(THEME_ETFS)
                      + ["QQQ", "SPY"]))
    n = snapshot_aum(syms)
    flows = fund_flows(syms)
    real = sum(1 for f in flows.values() if f["source"] == "aum")
    return {"snapshotted": n, "real_flow_ready": real,
            "of": len(syms)}
