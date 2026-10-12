"""Point-in-time fair-value backtest.

Runs the engine as_of a past date — the feature store only sees data
that existed then — and compares the scenario ladder against the
realized close. This is what the versioned run journal is for: every
row becomes a labeled training example (inputs → scenarios → realized
forward return) once enough history accumulates.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.database import db


def run_backtest(days_back: int = 90, limit: int = 80) -> Dict[str, Any]:
    from app.fair_value_v2.service import FairValueV2Service
    svc = FairValueV2Service()
    as_of = datetime.now(timezone.utc) - timedelta(days=days_back)

    symbols = [r["stock_symbol"] for r in db.execute_query(
        "SELECT DISTINCT stock_symbol FROM stock_insights_snapshots"
        " WHERE source='fmp_fundamentals' ORDER BY stock_symbol")]
    realized = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars"
        " ORDER BY symbol, date DESC")}
    px_then = {}
    for r in db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars"
            " WHERE date <= :d ORDER BY symbol, date DESC",
            {"d": as_of.date()}):
        px_then[r["symbol"]] = float(r["close"])

    rows: List[Dict[str, Any]] = []
    for sym in symbols[:limit]:
        if sym not in realized or sym not in px_then:
            continue
        try:
            res = svc.calculate(sym, as_of_ts=as_of)
        except Exception as exc:
            rows.append({"symbol": sym, "error": str(exc)[:80]})
            continue
        if not res.fair_value:
            rows.append({"symbol": sym, "status": "no_fv"})
            continue
        sc = res.scenario_fair_values or {}
        p0, p1 = px_then[sym], realized[sym]
        ret = p1 / p0 - 1
        rows.append({
            "symbol": sym,
            "regime": res.regime,
            "px_then": round(p0, 2), "px_now": round(p1, 2),
            "ret_pct": round(ret * 100, 1),
            "fv_base": round(res.fair_value, 2),
            "fv_expected": (round(res.expected_fair_value, 2)
                            if res.expected_fair_value else None),
            "bear": round(sc["bear"], 2) if sc.get("bear") else None,
            "bull": round(sc["bull"], 2) if sc.get("bull") else None,
            "gap_pct": round((res.fair_value / p0 - 1) * 100, 1),
            "realized_vs_base": round((p1 / res.fair_value - 1) * 100, 1),
            "within_band": (sc.get("bear") is not None
                            and sc.get("bull") is not None
                            and sc["bear"] <= p1 <= sc["bull"]),
            "flags": res.quality_flags,
        })

    ok = [r for r in rows if r.get("fv_base")]
    banded = [r for r in ok if r.get("within_band") is not None]
    in_band = sum(1 for r in banded if r["within_band"])
    cheap = [r for r in ok if (r["gap_pct"] or 0) > 15]
    cheap_won = sum(1 for r in cheap if (r["ret_pct"] or 0) > 0)
    rich = [r for r in ok if (r["gap_pct"] or 0) < -25]
    rich_fell = sum(1 for r in rich if (r["ret_pct"] or 0) < 0)
    errs = [abs(r["realized_vs_base"]) for r in ok]

    return {
        "as_of": as_of.date().isoformat(),
        "horizon_days": days_back,
        "n_symbols": len(ok),
        "no_fv": [r["symbol"] for r in rows if r.get("status") == "no_fv"],
        "coverage_pct": (round(100 * in_band / len(banded), 1)
                         if banded else None),
        "median_abs_err_pct": (round(sorted(errs)[len(errs) // 2], 1)
                               if errs else None),
        "cheap_hit_rate": (f"{cheap_won}/{len(cheap)}" if cheap else None),
        "rich_avoid_rate": (f"{rich_fell}/{len(rich)}" if rich else None),
        "rows": sorted(ok, key=lambda r: -(r["gap_pct"] or 0)),
    }


if __name__ == "__main__":
    import json
    import sys
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    out = run_backtest(d)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"},
                     indent=2, default=str))
    for r in out["rows"]:
        print(f"  {r['symbol']:>6} ret={r['ret_pct']:>+7.1f}%  "
              f"gap={r['gap_pct']:>+7.1f}%  base={r['fv_base']:>8} "
              f"bear={r['bear']} bull={r['bull']} "
              f"in_band={r['within_band']} {r.get('flags')}")
