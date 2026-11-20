"""Growth priced-in — the inverse solve over journaled FV runs.

The FV engine answers "what is it worth"; this answers "what must the
market be assuming, and can the business outrun it". Per spec
docs/specs/valuation-priced-in.md — Phase 1.

Per symbol, from the latest fair_value_v2_runs row:

  required_cagr    growth needed under OUR exit multiple + 10%/3y
                   hurdle — labeled honestly, not "the market's
                   forecast" (reverse-DCF implied growth is the
                   triangulation and ships alongside)
  implied_growth   from run.reverse_dcf — fcf path, or margin_path
                   for negative-FCF names (status taxonomy, never a
                   fabricated number)
  expectation_gap  forecast_cagr − required_cagr (pp)
  compression_drag (pe_exit/pe_now)^(1/n) − 1 — annualized cost of
                   multiple normalization; stored beside
                   expected_return_2y (the run's own total), never
                   conflated with it
  fv_bear/base/bull + valuation_dispersion + margin_of_safety
  score            0-100 priced-in-ness: high = little left to prove

Honesty rules (spec): None for invalid/missing inputs, never zero;
no EPS CAGR for unprofitable names — the margin_path note instead;
EPS consistency — forward EPS only pairs with forward-year horizons;
exit multiple = the engine's OWN justified multiple (fv/eps_fwd), so
the required-CAGR frame is consistent with our FV, not the market's.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

REQUIRED_RETURN = 0.10          # annual hurdle — parameter, not constant
HORIZON_YEARS = 3
_FORECAST_CLIP = (-0.50, 0.60)  # sanity bounds on any forecast CAGR
MODEL_VERSION = "priced_in.v1"


def _f(x) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _load(obj) -> Any:
    return json.loads(obj) if isinstance(obj, str) else obj


def required_eps_cagr(price: Optional[float],
                      starting_eps: Optional[float],
                      exit_pe: Optional[float],
                      required_return: float = REQUIRED_RETURN,
                      years: int = HORIZON_YEARS) -> Optional[float]:
    """g in P = EPS_fwd(1+g)^n × PE_exit / (1+r)^n — the growth the
    price demands under OUR chosen exit multiple and return hurdle.
    Rejects nonpositive EPS/PE/price → None, never a misleading CAGR."""
    p, e, x = _f(price), _f(starting_eps), _f(exit_pe)
    if not p or not e or not x or p <= 0 or e <= 0 or x <= 0:
        return None
    return (p * (1 + required_return) ** years / (e * x)) ** (1 / years) - 1


def _compression_drag(pe_normal: Optional[float],
                      pe_now: Optional[float],
                      years: int = HORIZON_YEARS) -> Optional[float]:
    """(PE_normal/PE_now)^(1/n) − 1 — annualized cost of the multiple
    normalizing. Negative = compression eats the return."""
    n, c = _f(pe_normal), _f(pe_now)
    if not n or not c or n <= 0 or c <= 0:
        return None
    return (n / c) ** (1 / years) - 1


def _score(gap: Optional[float], drag: Optional[float],
           mos: Optional[float]) -> Optional[float]:
    """0-100 priced-in-ness. gap>0 (forecast beats required) and MOS>0
    pull the score DOWN (attractive); negative gap and compression
    push it UP (expensive). High score = little left to prove."""
    if gap is None and drag is None and mos is None:
        return None
    s = 50.0
    if gap is not None:
        s -= gap * 100 * 2.0          # ±10pp gap → ∓20 pts
    if drag is not None:
        s -= drag * 100 * 1.5         # −15%/yr drag → +22 pts
    if mos is not None:
        s -= mos * 40.0               # +30% MOS → −12 pts
    return round(max(0.0, min(100.0, s)), 1)


def evaluate(symbol: str, as_of: Optional[date] = None) -> dict:
    """Compose the priced-in read for one symbol from its latest FV
    run. Everything degrades to None honestly — a thin run yields a
    thin row, journaled with its missing_inputs."""
    from app.database import db
    sym = symbol.upper()
    rows = db.execute_query(
        "SELECT run_id, as_of, fair_value, scenario_fair_values,"
        " spot_at_run, decision, reverse_dcf, relative_valuation,"
        " decision_scalars, regime, model_version"
        " FROM fair_value_v2_runs WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": sym})
    if not rows:
        return {"sector": None, "symbol": sym, "as_of": str(as_of or date.today()),
                "status": "no_fv_run", "missing_inputs": ["fv_run"]}
    run = dict(rows[0])
    scalars = _load(run.get("decision_scalars")) or {}
    scen = _load(run.get("scenario_fair_values")) or {}
    decision = _load(run.get("decision")) or {}
    reverse = _load(run.get("reverse_dcf")) or {}
    missing: list[str] = []

    spot = _f(run.get("spot_at_run"))
    if spot is None:                                   # fallback: latest close
        c = db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s"
            " AND date<=:d ORDER BY date DESC LIMIT 1",
            {"s": sym, "d": as_of or date.today()})
        spot = _f(c[0]["close"]) if c else None
    fv = _f(run.get("fair_value"))
    eps_fwd = _f(scalars.get("eps_forward"))
    bear, base, bull = (_f(scen.get(k)) for k in ("bear", "base", "bull"))

    # exit multiple — the engine's own justified P/E (fv/eps_fwd), so
    # required-CAGR is measured against OUR normal, not the market's
    exit_pe = (fv / eps_fwd
               if fv and eps_fwd and eps_fwd > 0 else None)
    pe_now = (spot / eps_fwd
              if spot and eps_fwd and eps_fwd > 0 else None)

    required = required_eps_cagr(spot, eps_fwd, exit_pe)

    # forecast CAGR — a driver-bridge collapse is the preferred leg
    # (provenance-backed, explains *why*), then analyst 1-y consensus,
    # then realized ttm growth as labeled proxy. Never manufactured
    # for negative-EPS names.
    forecast = _f(scalars.get("forward_growth_pct_1y"))
    forecast_src = "consensus_1y"
    driver_forecast = None
    try:
        from app.valuation.driver_bridge import latest as _dfl
        driver_forecast = _dfl(sym)
    except Exception:
        driver_forecast = None
    drv_base = None
    if driver_forecast:
        drv_base = ((driver_forecast.get("forecast") or {})
                    .get("revenue_growth") or {}).get("base")
    if drv_base is not None:
        forecast, forecast_src = _f(drv_base), "drivers"
    elif forecast is None:
        forecast = _f(scalars.get("eps_growth_ttm"))
        forecast_src = "realized_ttm_proxy"
    if forecast is not None:
        forecast = max(_FORECAST_CLIP[0], min(_FORECAST_CLIP[1], forecast))

    gap = (forecast - required
           if forecast is not None and required is not None else None)
    drag = _compression_drag(exit_pe, pe_now)
    mos = (fv / spot - 1) if fv and spot else None
    dispersion = ((bull - bear) / base
                  if bull and bear and base and base > 0 else None)

    # implied growth — surfaced from the run, status taxonomy intact
    implied = _f(reverse.get("implied_fcf_growth"))
    implied_status = reverse.get("status") or reverse.get("reason")
    margin_path = reverse.get("margin_path")
    if implied is None and margin_path:
        implied_status = "negative_fcf_margin_path"

    # expected total return — the run's own 2y number; drag is a
    # component of it, kept separate, never rederived here
    expected_ret = _f(decision.get("expected_return_2y"))

    for k, v in (("spot", spot), ("eps_forward", eps_fwd),
                 ("fv", fv), ("forecast", forecast)):
        if v is None:
            missing.append(k)

    score = _score(gap, drag, mos)
    return {
        "symbol": sym, "as_of": str(as_of or date.today()),
        "run_id": run.get("run_id"), "run_as_of": str(run.get("as_of")),
        "model_version": MODEL_VERSION,
        "price": spot, "eps_fwd": eps_fwd,
        "exit_pe": round(exit_pe, 2) if exit_pe else None,
        "pe_now": round(pe_now, 2) if pe_now else None,
        "forecast_cagr": (round(forecast, 4)
                          if forecast is not None else None),
        "forecast_src": forecast_src if forecast is not None else None,
        "required_cagr": (round(required, 4)
                          if required is not None else None),
        "implied_growth": implied, "implied_status": implied_status,
        "expectation_gap": round(gap, 4) if gap is not None else None,
        "compression_drag": round(drag, 4) if drag is not None else None,
        "expected_annual_return": expected_ret,
        "fv_bear": bear, "fv_base": base or fv, "fv_bull": bull,
        "valuation_dispersion": (round(dispersion, 3)
                                 if dispersion is not None else None),
        "margin_of_safety": round(mos, 4) if mos is not None else None,
        "score": score,
        "driver_forecast": (driver_forecast.get("forecast")
                            if driver_forecast else None),
        "missing_inputs": missing,
    }


def run(symbols: Optional[list[str]] = None) -> dict:
    """Daily journal — priced-in row per symbol with a fresh FV run."""
    from app.database import db
    if symbols is None:
        rows = db.execute_query(
            "SELECT DISTINCT symbol FROM fair_value_v2_runs"
            " WHERE as_of >= now() - interval '10 days'")
        symbols = [r["symbol"] for r in rows]
    out, errs = {}, []
    for sym in symbols:
        try:
            v = evaluate(sym)
            db.execute_update(
                "INSERT INTO growth_priced_in_daily (symbol, as_of,"
                " run_id, price, eps_fwd, exit_pe, pe_now, forecast_cagr,"
                " forecast_src, required_cagr, implied_growth,"
                " implied_status, expectation_gap, compression_drag,"
                " expected_annual_return, fv_bear, fv_base, fv_bull,"
                " valuation_dispersion, margin_of_safety, score,"
                " model_version, missing_inputs, driver_forecast, detail)"
                " VALUES (:s,:d,:rid,:p,:e,:x,:pn,:fc,:fs,:rc,:ig,:is_,"
                " :eg,:cd,:er,:fb,:fv,:fu,:vd,:mos,:sc,:mv,"
                " CAST(:mi AS jsonb),CAST(:df AS jsonb),"
                " CAST(:dt AS jsonb))"
                " ON CONFLICT (symbol, as_of) DO UPDATE SET"
                " run_id=EXCLUDED.run_id, price=EXCLUDED.price,"
                " required_cagr=EXCLUDED.required_cagr,"
                " expectation_gap=EXCLUDED.expectation_gap,"
                " compression_drag=EXCLUDED.compression_drag,"
                " driver_forecast=EXCLUDED.driver_forecast,"
                " score=EXCLUDED.score, detail=EXCLUDED.detail",
                {"s": sym, "d": v["as_of"], "rid": v["run_id"],
                 "p": v["price"], "e": v["eps_fwd"], "x": v["exit_pe"],
                 "pn": v["pe_now"], "fc": v["forecast_cagr"],
                 "fs": v["forecast_src"], "rc": v["required_cagr"],
                 "ig": v["implied_growth"], "is_": v["implied_status"],
                 "eg": v["expectation_gap"], "cd": v["compression_drag"],
                 "er": v["expected_annual_return"],
                 "fb": v["fv_bear"], "fv": v["fv_base"],
                 "fu": v["fv_bull"], "vd": v["valuation_dispersion"],
                 "mos": v["margin_of_safety"], "sc": v["score"],
                 "mv": v["model_version"],
                 "mi": json.dumps(v["missing_inputs"]),
                 "df": json.dumps(v.get("driver_forecast"), default=str),
                 "dt": json.dumps(v, default=str)})
            out[sym] = v["score"]
        except Exception as exc:
            errs.append(f"{sym}: {exc}")
    return {"evaluated": len(out), "errors": errs}


def read(symbol: str, days: int = 90) -> list[dict]:
    from app.database import db
    try:
        return db.execute_query(
            "SELECT symbol, as_of, price, eps_fwd, exit_pe, forecast_cagr,"
            " forecast_src, required_cagr, implied_growth,"
            " implied_status, expectation_gap, compression_drag,"
            " expected_annual_return, fv_bear, fv_base, fv_bull,"
            " valuation_dispersion, margin_of_safety, score,"
            " missing_inputs, driver_forecast"
            " FROM growth_priced_in_daily WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT :n",
            {"s": symbol.upper(), "n": days})
    except Exception:
        return []
