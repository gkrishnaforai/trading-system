"""FV v2 backtest — do stored fair values and buy_below gates predict?

Read-only over fair_value_v2_runs × fv_backtest_forwards. For each
horizon:

  fv_bias      median signed error of base FV vs realized end price
  fv_mae       median |error|
  bear_breach  share of runs whose min(path) <= bear FV (~25% target)
  gate_reach   share of runs where min(path) <= buy_below
  ret_in/out   median forward return for runs that were already inside
               the buy_below gate at run time vs outside it

Forward outcomes are materialized in `fv_backtest_forwards` — one
windowed SQL pass per refresh replaces the old O(runs × horizons)
per-run query pattern that timed out past ~1.5k runs. Callers may pass
`refresh=False` to read the materialized table as-is.
"""
from __future__ import annotations

import json
import statistics
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.database import db

DEFAULT_HORIZONS = [90, 180, 365]


def _median(xs: List[Optional[float]]) -> Optional[float]:
    xs = sorted(x for x in xs if x is not None)
    return statistics.median(xs) if xs else None


def refresh_forwards(symbol: Optional[str] = None,
                     horizons: Optional[List[int]] = None) -> int:
    """Materialize (run × horizon) forward outcomes in one pass.

    For each stored run: the min close inside the horizon window and the
    close nearest the horizon end (trading-day offset ≈ days×5/7).
    Returns the number of upserted rows. Safe to re-run — upserts on
    (symbol, as_of, horizon_days)."""
    horizons = horizons or DEFAULT_HORIZONS
    vals = ",".join(f"({int(h)})" for h in horizons)
    q = f"""
        INSERT INTO fv_backtest_forwards
            (symbol, as_of, horizon_days, end_px, min_close, n_bars)
        SELECT r.symbol, r.as_of::date, h.d,
               e.close, agg.lo, agg.n
        FROM fair_value_v2_runs r
        CROSS JOIN (VALUES {vals}) AS h(d)
        LEFT JOIN LATERAL (
            SELECT min(b.close) AS lo, count(*) AS n
            FROM daily_bars b
            WHERE b.symbol = r.symbol
              AND b.date > r.as_of::date
              AND b.date <= r.as_of::date + h.d
        ) agg ON true
        LEFT JOIN LATERAL (
            SELECT b.close
            FROM daily_bars b
            WHERE b.symbol = r.symbol
              AND b.date > r.as_of::date
            ORDER BY b.date ASC
            LIMIT 1 OFFSET GREATEST((h.d * 5 / 7) - 1, 0)
        ) e ON true
        WHERE r.fair_value IS NOT NULL AND r.spot_at_run > 0
    """
    params: Dict[str, Any] = {}
    if symbol:
        q += " AND r.symbol = :s"
        params["s"] = symbol.upper()
    q += """
        ON CONFLICT (symbol, as_of, horizon_days) DO UPDATE SET
            end_px = EXCLUDED.end_px,
            min_close = EXCLUDED.min_close,
            n_bars = EXCLUDED.n_bars,
            computed_at = now()
    """
    with db.get_session() as session:
        res = session.execute(text(q), params)
        return res.rowcount or 0


def _runs(symbol: Optional[str]):
    """Stored runs joined to their materialized forward outcomes."""
    q = ("SELECT r.symbol, r.as_of::date AS as_of, r.fair_value,"
         " r.expected_fair_value, r.spot_at_run, r.scenario_fair_values,"
         " r.decision, f.horizon_days, f.end_px, f.min_close"
         " FROM fair_value_v2_runs r"
         " JOIN fv_backtest_forwards f"
         "   ON f.symbol = r.symbol AND f.as_of = r.as_of::date"
         " WHERE r.fair_value IS NOT NULL AND r.spot_at_run > 0"
         "   AND f.end_px IS NOT NULL")
    params: Dict[str, Any] = {}
    if symbol:
        q += " AND r.symbol = :s"
        params["s"] = symbol.upper()
    q += " ORDER BY r.as_of"
    return db.execute_query(q, params)


def run_backtest(symbol: Optional[str] = None,
                 horizons: Optional[List[int]] = None,
                 refresh: bool = True,
                 per_symbol: bool = False) -> Dict[str, Any]:
    horizons = horizons or list(DEFAULT_HORIZONS)
    refreshed = None
    if refresh:
        try:
            refreshed = refresh_forwards(symbol=symbol, horizons=horizons)
        except Exception:
            refreshed = -1  # table absent on unmigrated deploys — degrade
    runs = _runs(symbol)

    # bucket rows by horizon — one row per (run, horizon)
    by_h: Dict[int, List[Dict[str, Any]]] = {h: [] for h in horizons}
    sym_stats: Dict[str, Dict[str, Any]] = {}
    total_run_ids = set()
    for r in runs:
        total_run_ids.add((r["symbol"], str(r["as_of"])))
        h = int(r["horizon_days"])
        if h in by_h:
            by_h[h].append(r)

    def _metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        biases, maes, ret_in, ret_out = [], [], [], []
        bear_hits = gate_hits = bear_n = gate_n = 0
        for r in rows:
            spot = float(r["spot_at_run"])
            fv = float(r["fair_value"])
            scen = r.get("scenario_fair_values") or {}
            if isinstance(scen, str):
                scen = json.loads(scen)
            dec = r.get("decision") or {}
            if isinstance(dec, str):
                dec = json.loads(dec)
            bb = dec.get("buy_below")
            bear = scen.get("bear")
            end_px = float(r["end_px"])
            lo = (float(r["min_close"])
                  if r.get("min_close") is not None else None)
            err = end_px / fv - 1
            biases.append(err)
            maes.append(abs(err))
            if bear is not None:
                bear_n += 1
                if lo is not None and lo <= float(bear):
                    bear_hits += 1
            if bb is not None:
                gate_n += 1
                if lo is not None and lo <= float(bb):
                    gate_hits += 1
            ret = end_px / spot - 1
            (ret_in if (bb and spot <= float(bb)) else ret_out).append(ret)
        n = len(rows)
        return {
            "n": n,
            "fv_bias": _median(biases), "fv_mae": _median(maes),
            "bear_breach": (bear_hits / bear_n) if bear_n else None,
            "gate_reach": (gate_hits / gate_n) if gate_n else None,
            "ret_inside_gate": _median(ret_in), "n_inside": len(ret_in),
            "ret_outside_gate": _median(ret_out), "n_outside": len(ret_out),
        }

    out: Dict[str, Any] = {
        "symbol": symbol, "horizons": [],
        "total_runs": len(total_run_ids),
        "forwards_refreshed": refreshed,
    }
    for h in horizons:
        m = _metrics(by_h.get(h) or [])
        m["days"] = h
        out["horizons"].append(m)

    if per_symbol:
        for h in horizons:
            for r in by_h.get(h) or []:
                s = sym_stats.setdefault(r["symbol"], {})
                s.setdefault(h, []).append(r)
        out["per_symbol"] = {
            s: {str(h): _metrics(rows) for h, rows in hs.items()}
            for s, hs in sorted(sym_stats.items())
        }
    return out
