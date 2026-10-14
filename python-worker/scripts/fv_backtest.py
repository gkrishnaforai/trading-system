"""FV v2 backtest — do stored fair values and buy_below gates predict?

Read-only. Joins every fair_value_v2_run with daily_bars forward
returns at +3/+6/+12 months and reports, per horizon:

  fv_bias        median signed error of base FV vs realized price
  fv_mae         median |error|
  bear_breach    % of horizons where price fell below bear FV
                 (~25% target — the scenario probability weight)
  gate_reach     % of runs where price dipped to buy_below within
                 horizon (was the gate ever actionable?)
  fwd_ret_gate   median forward return for runs where spot was
                 already <= buy_below at run time vs above it —
                 does the gate actually separate entries?

Usage (inside the python-worker container or with DATABASE_URL set):
    python scripts/fv_backtest.py [--symbol NVDA] [--horizons 90,180,365]
"""

import argparse
import json
import sys
import statistics

sys.path.insert(0, ".")

from app.database import db  # noqa: E402


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    return statistics.median(xs) if xs else None


def _fetch_runs(symbol=None):
    q = ("SELECT symbol, as_of::date AS as_of, fair_value,"
         " expected_fair_value, spot_at_run, scenario_fair_values,"
         " decision"
         " FROM fair_value_v2_runs"
         " WHERE fair_value IS NOT NULL AND spot_at_run > 0")
    params = {}
    if symbol:
        q += " AND symbol = :s"
        params["s"] = symbol.upper()
    q += " ORDER BY as_of"
    return db.execute_query(q, params)


def _forward(symbol, as_of, days):
    """min/max/end close in (as_of, as_of+days] — realized path."""
    rows = db.execute_query(
        "SELECT min(close) AS lo, max(close) AS hi,"
        "  (SELECT close FROM daily_bars WHERE symbol=:s"
        "   AND date > :d ORDER BY date ASC"
        "   LIMIT 1 OFFSET :off) AS end_px"
        " FROM daily_bars WHERE symbol=:s"
        "  AND date > :d AND date <= :d + :days",
        {"s": symbol, "d": as_of, "days": days,
         "off": max(0, int(days * 5 / 7) - 1)})
    r = rows[0] if rows else {}
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--horizons", default="90,180,365")
    args = ap.parse_args()
    horizons = [int(x) for x in args.horizons.split(",")]

    runs = _fetch_runs(args.symbol)
    if not runs:
        print("no runs")
        return

    print(f"{'h':>5} {'n':>4} {'fv_bias':>8} {'fv_mae':>7} "
          f"{'bear%':>6} {'gate%':>6} {'ret<=bb':>8} {'ret>bb':>8}")

    for h in horizons:
        biases, maes, bear_hits, gate_hits = [], [], 0, 0
        ret_in, ret_out, n_in, n_eval = [], [], 0, 0
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
                continue  # horizon not yet elapsed
            end_px = float(fwd["end_px"])
            lo = float(fwd["lo"]) if fwd["lo"] is not None else None
            n_eval += 1
            err = end_px / fv - 1
            biases.append(err)
            maes.append(abs(err))
            if bear and lo is not None and lo <= float(bear):
                bear_hits += 1
            if bb and lo is not None and lo <= float(bb):
                gate_hits += 1
            ret = end_px / spot - 1
            if bb and spot <= float(bb):
                ret_in.append(ret); n_in += 1
            else:
                ret_out.append(ret)
        if not n_eval:
            print(f"{h:>5} {0:>4}  — horizon not elapsed")
            continue
        f = lambda x: f"{x:+.1%}" if x is not None else "—"
        print(f"{h:>5} {n_eval:>4} {f(_median(biases)):>8} "
              f"{f(_median(maes)):>7} "
              f"{bear_hits / n_eval:>5.0%} {gate_hits / n_eval:>5.0%} "
              f"{f(_median(ret_in)):>8} {f(_median(ret_out)):>8}")


if __name__ == "__main__":
    main()
