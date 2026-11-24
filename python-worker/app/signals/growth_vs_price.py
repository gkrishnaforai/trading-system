"""growth_vs_price — the three-way comparison the review asked for.

The PEG table had a real defect: single-year FY27→28 growth as the
denominator mechanically rewards recovery-year names (MOD −10% then
+40% reads as "growth" that is really normalization). This module
recomputes the book three ways and keeps them separate:

    consensus   fwd P/E + PEG on analyst FY27/FY28 — what the market
                expects
    derived     driver_math implied growth — what the operating
                drivers support (only where an equation exists)
    normalized  P/E on the FY28 eps_low — the bear-analyst basis as
                a cycle proxy; the consensus-vs-low spread IS the
                cyclicality signal for MU/WDC/STX

Honesty rules:
- PEG denominator is the 2-yr CAGR from TTM EPS → FY28, never the
  one-year bounce
- recovery_year flag when FY27 EPS < TTM EPS — the "growth" is
  normalization, not secular
- cyclical flag on wide estimate dispersion — P/E on a peak-cycle
  average isn't a bargain
- loss-makers and bad-unit data excluded, loudly
- three rankings kept separate, never blended into one vote

run() journals the whole book daily; the table grades itself
against realized FY27/FY28 like every other call.
"""
from __future__ import annotations

import collections
import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_EPS_UNIT_FLAG = 0.5      # implied P/E below this = feed units broken


def _eps_ttm(db, sym: str) -> Optional[float]:
    r = db.execute_query(
        "SELECT eps_actual FROM earnings_data WHERE stock_symbol=:s"
        " AND eps_actual IS NOT NULL ORDER BY earnings_date DESC"
        " LIMIT 4", {"s": sym})
    if not r or len(r) < 4:
        return None
    return sum(float(x["eps_actual"]) for x in r)


def _rev_ttm(db, sym: str) -> Optional[float]:
    r = db.execute_query(
        "SELECT revenue_actual FROM earnings_data WHERE stock_symbol"
        "=:s AND revenue_actual IS NOT NULL ORDER BY earnings_date"
        " DESC LIMIT 4", {"s": sym})
    if not r or len(r) < 4:
        return None
    return sum(float(x["revenue_actual"]) for x in r)


def _estimates(db) -> dict:
    rows = db.execute_query(
        "SELECT DISTINCT ON (symbol, period_end) symbol, period_end,"
        " rev_avg, eps_avg, eps_low, eps_high, num_analysts"
        " FROM symbol_estimate_snapshots WHERE period_end IS NOT NULL"
        " ORDER BY symbol, period_end, as_of DESC") or []
    est = collections.defaultdict(dict)
    for r in rows:
        if r["period_end"].year in (2027, 2028):
            est[r["symbol"]][r["period_end"].year] = {
                "rev": float(r["rev_avg"]) if r["rev_avg"] else None,
                "eps": float(r["eps_avg"]) if r["eps_avg"] else None,
                "lo": float(r["eps_low"]) if r["eps_low"] else None,
                "hi": float(r["eps_high"]) if r["eps_high"] else None,
                "n": r["num_analysts"], "end": str(r["period_end"])}
    return est


def compute(symbols: Optional[list[str]] = None) -> dict[str, dict]:
    """Three-way comparison for every name with usable estimates."""
    from app.database import db
    if symbols is None:
        try:
            import yaml
            cfg = yaml.safe_load(open(
                "app/research/sectors/ai_infra.yaml"))
            symbols = sorted((cfg.get("symbol_map") or {}).keys())
        except Exception:
            symbols = []
    px = {r["symbol"]: float(r["close"]) for r in db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, close FROM daily_bars"
        " ORDER BY symbol, date DESC") or []}
    est = _estimates(db)

    # driver_math derived runs — implied growth where an equation ran
    derived: dict[str, dict] = {}
    for r in db.execute_query(
            "SELECT symbol, forecast->'derived' d FROM driver_forecasts"
            " WHERE as_of = current_date AND forecast ? 'derived'") or []:
        if r.get("d"):
            derived[r["symbol"]] = r["d"]

    out: dict[str, dict] = {}
    for s in symbols:
        e = est.get(s, {})
        e27, e28 = e.get(2027, {}), e.get(2028, {})
        p = px.get(s)
        row: dict[str, Any] = {"symbol": s}
        ttm_eps = _eps_ttm(db, s)
        ttm_rev = _rev_ttm(db, s)
        if ttm_rev:
            row["ttm_rev"] = round(ttm_rev / 1e9, 2)

        if not p or not e27.get("eps") or not e28.get("eps"):
            row["skip"] = "no price or FY27/28 estimates"
            out[s] = row
            continue
        if e27["eps"] <= 0 or e28["eps"] <= 0:
            row["skip"] = "loss-making — PEG doesn't apply"
            out[s] = row
            continue

        pe27, pe28 = p / e27["eps"], p / e28["eps"]
        if pe28 < _EPS_UNIT_FLAG:
            row["skip"] = ("implied P/E <0.5 — estimate units "
                           "inconsistent with price (data anomaly)")
            out[s] = row
            continue

        # ---- the fix: 2-yr CAGR from TTM → FY28, not the 1yr bounce
        yrs = max(1.0, (date.fromisoformat(e28["end"]).year
                        - date.today().year))
        base_eps = ttm_eps if ttm_eps and ttm_eps > 0 else e27["eps"]
        base_lbl = "ttm" if ttm_eps and ttm_eps > 0 else "fy27"
        yrs_from_base = yrs + (0.0 if base_lbl == "ttm" else -1.0)
        yrs_from_base = max(0.5, yrs_from_base)
        cagr = (e28["eps"] / base_eps) ** (1 / yrs_from_base) - 1
        g1y = e28["eps"] / e27["eps"] - 1

        row.update({
            "price": round(p, 1),
            "pe27": round(pe27, 1), "pe28": round(pe28, 1),
            "eps27": e27["eps"], "eps28": e28["eps"],
            "growth_1y": round(g1y, 3),
            "growth_cagr": round(cagr, 3),
            "cagr_base": base_lbl,
            "peg_1y": round(pe28 / (g1y * 100), 2) if g1y > 0 else None,
            "peg_cagr": round(pe28 / (cagr * 100), 2)
            if cagr > 0 else None,
            "analysts": e28.get("n"),
        })

        # recovery flag — FY27 EPS below TTM = the growth is
        # normalization off a dipped base, not secular
        if ttm_eps and e27["eps"] < ttm_eps * 0.90:
            row["recovery_year"] = True
            row["note"] = ("FY27 below TTM — FY28 'growth' is "
                           "normalization, not secular")

        # estimate reliability — coverage + dispersion
        lo, hi = e28.get("lo"), e28.get("hi")
        if lo and hi and e28["eps"] > 0:
            disp = (hi - lo) / e28["eps"]
            row["eps_dispersion"] = round(disp, 2)
            row["est_reliability"] = (
                "thin" if (e28.get("n") or 0) < 6 else
                "wide_dispersion" if disp > 0.5 else "ok")
            # normalized proxy — P/E on the bear-analyst FY28 EPS;
            # the avg-vs-low gap is the cyclicality signal
            if lo > 0:
                row["normalized_pe_proxy"] = round(p / lo, 1)
                row["cyclical_flag"] = disp > 0.5

        # derived — driver_math where an equation ran
        d = derived.get(s)
        if d and d.get("implied_growth") is not None:
            row["derived_implied_growth"] = d["implied_growth"]
            cons_g = (e27["rev"] / ttm_rev - 1) if (
                e27.get("rev") and ttm_rev) else None
            if cons_g is not None:
                row["consensus_vs_derived"] = round(
                    cons_g - d["implied_growth"], 3)
        out[s] = row
    return out


def rankings(comp: dict[str, dict]) -> dict[str, list]:
    """Three separate rankings — never blended."""
    usable = {s: r for s, r in comp.items() if "skip" not in r}
    by_peg = sorted(
        ((s, r["peg_cagr"]) for s, r in usable.items()
         if r.get("peg_cagr")), key=lambda x: x[1])
    by_growth = sorted(
        ((s, r["growth_cagr"]) for s, r in usable.items()
         if r.get("growth_cagr")), key=lambda x: -x[1])
    durable = sorted(
        ((s, -r.get("eps_dispersion") or -1)
         for s, r in usable.items()
         if r.get("est_reliability") == "ok"
         and not r.get("cyclical_flag")
         and (r.get("analysts") or 0) >= 8),
        key=lambda x: x[1])
    return {"growth_at_price": [s for s, _ in by_peg],
            "fundamental_growth": [s for s, _ in by_growth],
            "risk_adjusted": [s for s, _ in durable]}


def run(persist: bool = True) -> dict:
    from app.database import db
    comp = compute()
    ranks = rankings(comp)
    if persist:
        db.execute_update(
            "INSERT INTO growth_compare_daily (as_of, payload)"
            " VALUES (current_date, CAST(:p AS jsonb))"
            " ON CONFLICT (as_of) DO UPDATE SET payload=EXCLUDED.payload",
            {"p": __import__("json").dumps(
                {"names": comp, "rankings": ranks}, default=str)})
    return {"names": len(comp),
            "usable": sum(1 for r in comp.values() if "skip" not in r),
            "rankings": ranks, "comp": comp}


def latest() -> Optional[dict]:
    from app.database import db
    r = db.execute_query(
        "SELECT as_of, payload FROM growth_compare_daily"
        " ORDER BY as_of DESC LIMIT 1")
    return r[0] if r else None
