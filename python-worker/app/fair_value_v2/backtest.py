"""FV v2 backtest — do stored fair values and buy_below gates predict?

Read-only over fair_value_v2_runs × daily_bars. For each horizon:

  fv_bias      median signed error of base FV vs realized end price
  fv_mae       median |error|
  bear_breach  share of runs whose min(path) <= bear FV (~25% target)
  gate_reach   share of runs where min(path) <= buy_below
  ret_in/out   median forward return for runs that were already inside
               the buy_below gate at run time vs outside it

Pure computation + SQL — imported by the admin endpoint and the CLI
script so both report identical numbers.
"""
from __future__ import annotations

import json
import statistics
from typing import Any, Dict, List, Optional

from app.database import db


def _median(xs: List[Optional[float]]) -> Optional[float]:
    xs = sorted(x for x in xs if x is not None)
    return statistics.median(xs) if xs else None


def _runs(symbol: Optional[str]):
    q = ("SELECT symbol, as_of::date AS as_of, fair_value,"
         " expected_fair_value, spot_at_run, scenario_fair_values,"
         " decision"
         " FROM fair_value_v2_runs"
         " WHERE fair_value IS NOT NULL AND spot_at_run > 0")
    params: Dict[str, Any] = {}
    if symbol:
        q += " AND symbol = :s"
        params["s"] = symbol.upper()
    q += " ORDER BY as_of"
    return db.execute_query(q, params)


def _forward(symbol: str, as_of, days: int) -> Dict[str, Any]:
    rows = db.execute_query(
        "SELECT min(close) AS lo,"
        "  (SELECT close FROM daily_bars WHERE symbol=:s"
        "   AND date > :d ORDER BY date ASC"
        "   LIMIT 1 OFFSET :off) AS end_px"
        " FROM daily_bars WHERE symbol=:s"
        "  AND date > :d AND date <= :d + :days",
        {"s": symbol, "d": as_of, "days": days,
         "off": max(0, int(days * 5 / 7) - 1)})
    return rows[0] if rows else {}


def run_backtest(symbol: Optional[str] = None,
                 horizons: Optional[List[int]] = None) -> Dict[str, Any]:
    horizons = horizons or [90, 180, 365]
    runs = _runs(symbol)
    out: Dict[str, Any] = {"symbol": symbol, "horizons": [],
                           "total_runs": len(runs)}
    for h in horizons:
        biases, maes, bear_hits, gate_hits = [], [], 0, 0
        ret_in, ret_out = [], []
        n_eval = 0
        for r in runs:
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
            fwd = _forward(r["symbol"], r["as_of"], h)
            if not fwd or fwd.get("end_px") is None:
                continue
            end_px = float(fwd["end_px"])
            lo = float(fwd["lo"]) if fwd.get("lo") is not None else None
            n_eval += 1
            err = end_px / fv - 1
            biases.append(err)
            maes.append(abs(err))
            if bear and lo is not None and lo <= float(bear):
                bear_hits += 1
            if bb and lo is not None and lo <= float(bb):
                gate_hits += 1
            ret = end_px / spot - 1
            (ret_in if (bb and spot <= float(bb)) else ret_out).append(ret)
        out["horizons"].append({
            "days": h, "n": n_eval,
            "fv_bias": _median(biases), "fv_mae": _median(maes),
            "bear_breach": (bear_hits / n_eval) if n_eval else None,
            "gate_reach": (gate_hits / n_eval) if n_eval else None,
            "ret_inside_gate": _median(ret_in), "n_inside": len(ret_in),
            "ret_outside_gate": _median(ret_out), "n_outside": len(ret_out),
        })
    return out
