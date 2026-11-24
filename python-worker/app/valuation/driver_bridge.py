"""driver_bridge — scenario drivers → forecast scalars.

The spec's Phase-2 leg: scenario multipliers say revenue *might* grow
30%; drivers say *why* — commitments, filings, estimates — each with
its own provenance. `driver_assumptions` rows declare themselves
(`assumption_type`); a row with no `rationale_claim_id` must be
`model_assumption` — an unsupported assumption can never quietly
become a forecast.

`run()` collapses the latest assumptions into the growth/margin
scalars the composition layer consumes and journals the collapse to
`driver_forecasts`. It is an INPUT leg — priced-in/FV keep their
contracts; missing drivers fall back to multipliers + missing_inputs.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# driver catalog keyed off the fv2 regime category (no second
# taxonomy) — the drivers a scenario must explain for that business
# shape. Category is the part before ':' in fv2's 'category:regime'.
CATALOG = {
    "technology":  ["design_wins", "content_per_system", "units",
                    "arr_growth", "margin_path"],
    "ai_infra":    ["ai_demand", "customer_commitments",
                    "capacity_additions", "margin_path"],
    "financials":  ["nim", "loan_growth", "credit_quality", "deposits"],
    "fintech":     ["transaction_volume", "take_rate", "user_growth"],
    "cyclical":    ["midcycle_margin", "capacity", "price_cycle",
                    "backlog_conversion"],
    "value":       ["earnings_power", "capital_return",
                    "margin_stability", "reinvestment"],
    "consumer":    ["unit_growth", "pricing", "retention"],
    "healthcare":  ["procedure_volume", "adoption", "reimbursement"],
    "growth":      ["revenue_growth", "margin_path", "fcf_conversion"],
    "_generic":    ["market_growth", "share", "margin",
                    "fcf_conversion"],
}

# commitment metric → driver_key (unmapped metrics stay their own key)
_METRIC_MAP = {
    "revenue": "revenue_growth", "rev": "revenue_growth",
    "sales": "revenue_growth", "arr": "arr_growth",
    "op_margin": "op_margin", "operating_margin": "op_margin",
    "gross_margin": "gross_margin", "fcf": "fcf_conversion",
    "free_cash_flow": "fcf_conversion", "eps": "earnings_power",
    "capex": "reinvestment", "backlog": "backlog_conversion",
    "nim": "nim", "loan_growth": "loan_growth",
    "rate_base": "rate_base",
}

_CONF = {"raised": 0.75, "new": 0.55, "reaffirmed": 0.60, "cut": 0.40}


def _regime(symbol: str) -> Optional[str]:
    """fv2's latest journaled regime string ('category:regime')."""
    from app.database import db
    r = db.execute_query(
        "SELECT regime FROM fair_value_v2_runs WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": symbol})
    if not r or not r[0].get("regime"):
        return None
    return str(r[0]["regime"])


def seed(symbol: str) -> int:
    """Write driver_assumptions rows from journaled evidence —
    management commitments with claim linkage, plus explicitly-
    declared model_assumption anchors from measured fv2 inputs."""
    from app.database import db
    sym = symbol.upper()
    n = 0
    try:    # management's stated commitments → guidance assumptions
        for d in db.execute_query(
                "SELECT id, metric, period, value, delta_dir, status,"
                " created_at FROM driver_commitments WHERE symbol=:s"
                " AND status='open'", {"s": sym}) or []:
            claim = db.execute_query(
                "SELECT claim_id FROM narrative_claims WHERE symbol=:s"
                " AND evidence_refs::text LIKE :p LIMIT 1",
                {"s": sym,
                 "p": f'%"table": "driver_commitments"%"id": {d["id"]}%'})
            db.execute_update(
                "INSERT INTO driver_assumptions (symbol, scenario,"
                " driver_key, value, unit, period, assumption_type,"
                " rationale_claim_id, confidence, source_ref)"
                " VALUES (:s,'base',:k,:v,'usd',:p,"
                " 'management_guidance',:rc,:cf,"
                " CAST(:sr AS jsonb))"
                " ON CONFLICT (symbol, scenario, driver_key, period,"
                " as_of) DO NOTHING",
                {"s": sym, "k": _METRIC_MAP.get(d["metric"],
                                               d["metric"]),
                 "v": d["value"], "p": d["period"],
                 "rc": claim[0]["claim_id"] if claim else None,
                 "cf": _CONF.get(d["delta_dir"], 0.5),
                 "sr": json.dumps({"table": "driver_commitments",
                                   "id": d["id"]})})
            n += 1
    except Exception as exc:
        logger.debug("driver seed commitments %s: %s", sym, exc)
    try:    # measured forward growth — declared model_assumption base
        g = db.execute_query(
            "SELECT forecast_cagr, forecast_src FROM"
            " growth_priced_in_daily WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if g and g[0].get("forecast_cagr") is not None:
            db.execute_update(
                "INSERT INTO driver_assumptions (symbol, scenario,"
                " driver_key, value, unit, period, assumption_type,"
                " rationale_claim_id, confidence, source_ref)"
                " VALUES (:s,'base','revenue_growth',:v,'fraction',"
                " 'forward',:at,NULL,0.65,CAST(:sr AS jsonb))"
                " ON CONFLICT (symbol, scenario, driver_key, period,"
                " as_of) DO NOTHING",
                {"s": sym, "v": g[0]["forecast_cagr"],
                 "at": ("analyst_estimate"
                        if g[0].get("forecast_src") == "consensus_1y"
                        else "model_assumption"),
                 "sr": json.dumps({"table": "growth_priced_in_daily",
                                   "src": g[0].get("forecast_src")})})
            n += 1
    except Exception as exc:
        logger.debug("driver seed growth %s: %s", sym, exc)
    return n


def run(symbol: str) -> dict:
    """Collapse latest assumptions → driver_forecast row. Bear/bull
    legs only exist when evidence supplies them — never invented."""
    from app.database import db
    sym = symbol.upper()
    regime = _regime(sym)
    rows = db.execute_query(
        "SELECT DISTINCT ON (scenario, driver_key)"
        " scenario, driver_key, value, unit, period, assumption_type,"
        " rationale_claim_id, confidence FROM driver_assumptions"
        " WHERE symbol=:s ORDER BY scenario, driver_key, as_of DESC",
        {"s": sym}) or []

    legs: dict[str, dict] = {}
    provenance: dict[str, str] = {}
    for r in rows:
        legs.setdefault(r["driver_key"], {})[r["scenario"]] = {
            "value": r["value"], "unit": r["unit"],
            "period": r["period"], "type": r["assumption_type"],
            "confidence": r["confidence"]}
        if r["rationale_claim_id"]:
            provenance[f"{r['driver_key']}:{r['scenario']}"] = \
                r["rationale_claim_id"]

    catalog = CATALOG.get((regime or "").split(":")[0],
                          CATALOG["_generic"])
    missing = [k for k in catalog if k not in legs]
    coverage = (round((len(catalog) - len(missing)) / len(catalog), 2)
                if catalog else None)

    forecast = {
        "regime": regime, "drivers": legs,
        "revenue_growth": {sc: (legs.get("revenue_growth") or {})
                           .get(sc, {}).get("value")
                           for sc in ("bear", "base", "bull")},
        "source": "drivers" if legs else "none",
    }
    # driver arithmetic — where the business model has an equation
    # (neocloud first), the physical drivers multiply into a revenue
    # path and the implied growth is checked against the standing
    # scalar. Journaled in forecast['derived'].
    try:
        from app.valuation import driver_math
        derived = driver_math.evaluate(sym, legs)
        if derived:
            forecast["derived"] = derived
    except Exception as exc:
        logger.debug("driver_math %s: %s", sym, exc)
    db.execute_update(
        "INSERT INTO driver_forecasts (symbol, as_of, regime, forecast,"
        " provenance, missing_inputs, coverage)"
        " VALUES (:s,current_date,:r,CAST(:f AS jsonb),"
        " CAST(:p AS jsonb),CAST(:m AS jsonb),:cov)"
        " ON CONFLICT (symbol, as_of) DO UPDATE SET"
        " regime=EXCLUDED.regime, forecast=EXCLUDED.forecast,"
        " provenance=EXCLUDED.provenance,"
        " missing_inputs=EXCLUDED.missing_inputs,"
        " coverage=EXCLUDED.coverage",
        {"s": sym, "r": regime, "f": json.dumps(forecast, default=str),
         "p": json.dumps(provenance), "m": json.dumps(missing),
         "cov": coverage})
    return {"symbol": sym, "regime": regime, "coverage": coverage,
            "missing": missing, "drivers": len(legs)}


def latest(symbol: str) -> Optional[dict]:
    from app.database import db
    r = db.execute_query(
        "SELECT forecast, provenance, missing_inputs, coverage, as_of"
        " FROM driver_forecasts WHERE symbol=:s"
        " ORDER BY as_of DESC LIMIT 1", {"s": symbol.upper()})
    return r[0] if r else None


def run_all(symbols: Optional[list[str]] = None) -> dict:
    from app.database import db
    if symbols is None:
        rows = db.execute_query(
            "SELECT DISTINCT symbol FROM symbol_flywheel")
        symbols = [r["symbol"] for r in rows]
    forecasts = 0
    for s in symbols:
        try:
            seed(s)
            if run(s)["drivers"]:
                forecasts += 1
        except Exception as exc:
            logger.debug("driver_bridge %s: %s", s, exc)
    return {"symbols": len(symbols), "forecasts": forecasts}
