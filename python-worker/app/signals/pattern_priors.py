"""Pattern priors — "how did THIS setup work on THIS stock before?"

Institutional desk version of prediction: nobody forecasts prices;
they stack probabilistic edges. The classifier is deterministic +
stateless, so its full history is replayable — walk every past bar,
classify the state + dip phase as-of that day, then measure what the
stock actually did over the next 10/20 trading days.

Two sample streams:
  tape priors   (state | dip_phase) entry days → fwd 10d/20d return
  event priors  focus_events (contracts/upgrades/products/8-Ks)
                → fwd returns after the event date

Persisted per symbol AND pooled ('__ALL__') — per-symbol stats need
n>=4 to trust; pooled covers thin symbols.

Board/GARP read `prior_for()` and turn it into a bounded score nudge:
a setup that historically paid gets a bonus; one that kept failing
gets a penalty. Priors inform, they never decide alone.
"""
from __future__ import annotations

import logging
import statistics as st
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

_H = 20          # forward horizon (trading days)
_LOOKBACK = 320  # replay window (trading days ≈ 15mo)


def _fwd(bars, i: int, horizon: int) -> tuple[float, float, float]:
    px = bars[i].close
    n = len(bars)
    r10 = bars[min(i + 10, n - 1)].close / px - 1
    r20 = bars[min(i + horizon, n - 1)].close / px - 1
    mae = (min(b.low for b in bars[i + 1:i + horizon + 1]) / px - 1
           if i + 1 < n else 0.0)
    return r10, r20, mae


def _tech_frame(bars) -> dict:
    """One O(n) vectorized pass producing every field classify() reads,
    as a per-day frame — the same math _technicals/_macd_hist_prev
    compute scalar-by-scalar. Replay then evaluates day i by lookup
    instead of rescanning the window (was O(n²) — ~31ms × 275 days)."""
    import pandas as pd
    from app.indicators.momentum import calculate_rsi, calculate_macd
    c = pd.Series([b.close for b in bars], dtype=float)
    h = pd.Series([b.high for b in bars], dtype=float)
    s50, s200 = c.rolling(50).mean(), c.rolling(200).mean()
    m20, sd20 = c.rolling(20).mean(), c.rolling(20).std()
    sd20 = sd20.where(sd20 != 0)                    # sd20==0 → pct_b None
    _, _, hist = calculate_macd(c)
    return {"price": c, "sma50": s50, "sma200": s200,
            "vs_sma50": c / s50 - 1, "vs_sma200": c / s200 - 1,
            "rsi14": calculate_rsi(c, window=14), "macd_hist": hist,
            "hist_prev": hist.shift(5),           # _macd_hist_prev(back=5)
            "pct_b": (c - (m20 - 2 * sd20)) / (4 * sd20),
            "dd52w": c / h.rolling(252, min_periods=1).max() - 1}


def _row_tech(fr: dict, i: int) -> Optional[dict]:
    """Day-i tech dict from the frame — None mirrors _technicals' None
    semantics so classify()'s own gates stay the authority."""
    import pandas as pd
    def v(col):
        x = fr[col].iloc[i]
        return None if pd.isna(x) else float(x)
    return {"price": v("price"), "sma50": v("sma50"),
            "sma200": v("sma200"), "vs_sma50": v("vs_sma50"),
            "vs_sma200": v("vs_sma200"), "rsi14": v("rsi14"),
            "macd_hist": v("macd_hist"),
            "bollinger": {"pct_b": v("pct_b")}, "dd52w": v("dd52w")}


def replay_symbol(sym: str, bars, lookback: int = _LOOKBACK
                  ) -> list[dict[str, Any]]:
    """Walk back through bars, classify each day, record forward
    returns at state-ENTRY days (consecutive days in the same state
    aren't new samples)."""
    from app.signals.momentum_regime import classify, dip_health
    import pandas as pd

    n = len(bars)
    out = []
    prev_state = None
    fr = _tech_frame(bars)                       # O(n) once per symbol
    # sma200 needs 205+ closes — earlier windows can only classify
    # 'unknown', so skip them entirely
    for i in range(max(205, n - lookback), n - _H):
        win = bars[:i + 1]
        try:
            tech = _row_tech(fr, i)
            hp = fr["hist_prev"].iloc[i]
            hp = None if pd.isna(hp) else float(hp)
            state = classify(tech, hp, win)
            entry = state != prev_state
            prev_state = state
            if not entry:
                continue
            dp = dip_health(tech, hp, win)
            r10, r20, mae = _fwd(bars, i, _H)
            out.append({"key": f"{state}|{(dp or {}).get('dip_phase') or 'none'}",
                        "r10": r10, "r20": r20, "mae": mae})
        except Exception:
            continue
    return out


def _agg(samples: list[dict]) -> Optional[dict]:
    if len(samples) < 2:
        return None
    r10 = [s["r10"] for s in samples]
    return {"n": len(samples),
            "hit_rate_10d": round(sum(1 for r in r10 if r > 0)
                                  / len(r10), 3),
            "med_ret_10d": round(st.median(r10), 4),
            "med_ret_20d": round(st.median([s["r20"] for s in samples]), 4),
            "med_mae": round(st.median([s["mae"] for s in samples]), 4)}


_EVT_BUCKET = {
    "analyst_upgrade": "analyst_up", "analyst_downgrade": "analyst_down",
    "price_target": "pt_change", "product": "product",
    "contract": "contract", "partnership": "contract",
    "sec_filing": "sec", "guidance": "guidance"}


def event_samples(sym: str, bars, events: list[dict]
                  ) -> list[dict[str, Any]]:
    """Event→outcome attribution: forward returns after each stored
    material event — 'do upgrades actually move THIS stock?'"""
    idx = {b.date: i for i, b in enumerate(bars)}
    out = []
    for e in events:
        d = (e.get("published_at") or e.get("detected_at"))
        if isinstance(d, datetime):
            d = d.date()
        if not isinstance(d, date):
            continue
        i = idx.get(d)
        if i is None:                      # event on a non-trading day
            later = [x for x in idx if x > d]
            i = idx[min(later)] if later else None
        if i is None or i + 10 >= len(bars):
            continue
        bucket = _EVT_BUCKET.get(e.get("event_type") or "", "other")
        r10, r20, mae = _fwd(bars, i, _H)
        out.append({"key": f"evt:{bucket}", "r10": r10, "r20": r20,
                    "mae": mae})
    return out


def compute_priors() -> dict[str, Any]:
    """Daily batch: replay tape history + attribute events for every
    flagged symbol, upsert per-symbol + pooled priors."""
    from types import SimpleNamespace
    from app.database import db
    import pandas as pd

    syms = [r["symbol"] for r in db.execute_query(
        "SELECT symbol FROM stocks WHERE momentum_state IS NOT NULL "
        "ORDER BY symbol")]
    if not syms:
        return {"symbols": 0}
    events = {r["symbol"]: [] for r in db.execute_query(
        "SELECT DISTINCT symbol FROM focus_events")}
    for r in db.execute_query(
            "SELECT symbol, event_type, published_at, detected_at "
            "FROM focus_events WHERE materiality >= 3 "
            "ORDER BY published_at"):
        events.setdefault(r["symbol"], []).append(r)

    # canonical bars — momentum's daily fetch populates daily_bars;
    # thin/missing symbols get a one-time live top-up inside load()
    from app.market_data import bars as bars_mod
    books = bars_mod.load(syms, days=550)
    pooled: dict[str, list] = {}
    done = 0
    for s in syms:
        try:
            bars = books.get(s) or []
            if len(bars) < 120:
                continue
            samples = replay_symbol(s, bars)
            samples += event_samples(s, bars, events.get(s) or [])
            by_key: dict[str, list] = {}
            for smp in samples:
                by_key.setdefault(smp["key"], []).append(smp)
                pooled.setdefault(smp["key"], []).append(smp)
            for key, lst in by_key.items():
                a = _agg(lst)
                if a:
                    db.execute_update(
                        "INSERT INTO pattern_priors"
                        " (symbol, pattern_key, n, hit_rate_10d,"
                        "  med_ret_10d, med_ret_20d, med_mae, computed_at)"
                        " VALUES (:y,:k,:n,:h,:m10,:m20,:mae,now())"
                        " ON CONFLICT (symbol, pattern_key) DO UPDATE"
                        " SET n=:n, hit_rate_10d=:h, med_ret_10d=:m10,"
                        "     med_ret_20d=:m20, med_mae=:mae,"
                        "     computed_at=now()",
                        {"y": s, "k": key, **{kk: a[kk] for kk in
                                             ("n", "hit_rate_10d",
                                              "med_ret_10d",
                                              "med_ret_20d", "med_mae")},
                         "h": a["hit_rate_10d"], "m10": a["med_ret_10d"],
                         "m20": a["med_ret_20d"], "mae": a["med_mae"],
                         "n": a["n"]})
            done += 1
        except Exception as exc:
            logger.debug("priors %s: %s", s, exc)
    for key, lst in pooled.items():
        a = _agg(lst)
        if a:
            db.execute_update(
                "INSERT INTO pattern_priors"
                " (symbol, pattern_key, n, hit_rate_10d,"
                "  med_ret_10d, med_ret_20d, med_mae, computed_at)"
                " VALUES ('__ALL__',:k,:n,:h,:m10,:m20,:mae,now())"
                " ON CONFLICT (symbol, pattern_key) DO UPDATE"
                " SET n=:n, hit_rate_10d=:h, med_ret_10d=:m10,"
                "     med_ret_20d=:m20, med_mae=:mae, computed_at=now()",
                {"k": key, "n": a["n"], "h": a["hit_rate_10d"],
                 "m10": a["med_ret_10d"], "m20": a["med_ret_20d"],
                 "mae": a["med_mae"]})
    return {"symbols": done, "pooled_keys": len(pooled),
            "at": datetime.now().isoformat(timespec="seconds")}


def prior_for(sym: str, pattern_key: str) -> Optional[dict]:
    """Best available prior: per-symbol if n>=4, else pooled."""
    from app.database import db
    for scope, s in (("symbol", sym), ("pooled", "__ALL__")):
        rows = db.execute_query(
            "SELECT n, hit_rate_10d, med_ret_10d, med_ret_20d, med_mae "
            "FROM pattern_priors WHERE symbol=:s AND pattern_key=:k",
            {"s": s, "k": pattern_key})
        if rows and rows[0]["n"] >= (4 if scope == "symbol" else 8):
            return {**rows[0], "scope": scope}
    return None
