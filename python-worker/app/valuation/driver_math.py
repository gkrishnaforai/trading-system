"""driver_math — quantified driver arithmetic per business model.

driver_bridge collapses assumptions into scalars; this layer does
the multiplication — the reason a neocloud's 'revenue_growth 60%'
claim is checkable instead of taken:

    neocloud  revenue_fwd = contracted_revenue
                        + capacity_mw × rev_per_mw_yr × utilization

    rev_per_mw_yr resolves deep when granular drivers exist:
        gpu_per_mw × price_per_gpu_hour × 8760h

Honesty rules:
- every input reports its assumption_type (management_guidance /
  analyst_estimate / model_assumption) — the equation never hides
  which leg is a guess
- utilization missing → the result is reported as the full-capacity
  CEILING, not a forecast — no silent 90% defaults
- derived growth is compared to the standing scalar assumption:
  divergence is the signal the scalar was never grounded
- no inputs → no block, nothing fabricated

evaluate() is called from driver_bridge.run() with the legs it
already assembled; results journal inside forecast['derived'].
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# industry prior for AI-cloud revenue intensity — declared as a
# model_assumption everywhere it lands, never presented as measured.
# NBIS-class pricing runs ~$10-14M per energized MW per year.
_REV_PER_MW_PRIOR = {"lo": 8e6, "mid": 11e6, "hi": 14e6}
_HOURS_YR = 8760


def _base(legs: dict, key: str) -> Optional[dict]:
    """Latest base-scenario leg for a driver_key."""
    return (legs.get(key) or {}).get("base")


def _ttm_revenue(sym: str) -> Optional[float]:
    """TTM revenue from the last four reported quarters — same
    basis convention as the EPS fix, never a provider blend."""
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT revenue_actual FROM earnings_data"
            " WHERE stock_symbol=:s AND revenue_actual IS NOT NULL"
            " ORDER BY earnings_date DESC LIMIT 4", {"s": sym})
        if not r or len(r) < 4:
            return None
        return sum(float(x["revenue_actual"]) for x in r)
    except Exception:
        return None


def _neocloud(sym: str, legs: dict) -> dict:
    inputs: dict[str, dict] = {}
    missing: list[str] = []

    for key in ("contracted_revenue", "capacity_mw", "gpu_per_mw",
                "price_per_gpu_hour", "utilization", "rev_per_mw_yr"):
        leg = _base(legs, key)
        if leg and leg.get("value") is not None:
            inputs[key] = {"value": leg["value"], "type": leg["type"],
                           "confidence": leg.get("confidence")}
        else:
            missing.append(key)

    # rev_per_mw — explicit input, else derived deep from GPU
    # economics, else the labeled industry prior.
    rpm = inputs.get("rev_per_mw_yr", {}).get("value")
    rpm_src = "input"
    if rpm is None:
        gpm = inputs.get("gpu_per_mw", {}).get("value")
        pph = inputs.get("price_per_gpu_hour", {}).get("value")
        if gpm and pph:
            rpm = gpm * pph * _HOURS_YR
            rpm_src = "derived_gpu_hours"
        else:
            rpm = _REV_PER_MW_PRIOR["mid"]
            rpm_src = "industry_prior"

    cap = inputs.get("capacity_mw", {}).get("value")
    contracted = inputs.get("contracted_revenue", {}).get("value") or 0.0
    util = inputs.get("utilization", {}).get("value")

    if cap is None:
        return {"module": "neocloud", "formula":
                "contracted + capacity_mw × rev_per_mw × util",
                "missing": missing,
                "note": "no capacity_mw — equation can't run"}

    ceiling = contracted + cap * rpm          # util = 1.0
    rev_fwd = contracted + cap * rpm * util if util else None

    out: dict[str, Any] = {
        "module": "neocloud",
        "formula": "contracted + capacity_mw × rev_per_mw × util",
        "inputs": inputs, "missing": missing,
        "rev_per_mw_yr": {"value": round(rpm), "source": rpm_src},
        "revenue_full_capacity": round(ceiling),
        "revenue_forward": round(rev_fwd) if rev_fwd else None,
        "capacity_kind": ("utilization_adjusted" if util
                          else "ceiling_utilization_missing"),
    }

    # the check that makes this worth computing — does the implied
    # growth support the standing scalar assumption? Ceiling fires
    # whenever TTM exists; the utilization-adjusted implied only
    # when a real utilization input does.
    ttm = _ttm_revenue(sym)
    standing = _base(legs, "revenue_growth")
    if ttm:
        out["ttm_revenue"] = round(ttm)
        out["implied_growth_ceiling"] = round(ceiling / ttm - 1, 3)
    if ttm and rev_fwd:
        implied = rev_fwd / ttm - 1
        out["implied_growth"] = round(implied, 3)
        if standing and standing.get("value") is not None:
            sg = standing["value"]
            out["standing_growth"] = sg
            out["growth_divergence"] = round(implied - sg, 3)
            out["divergence_read"] = (
                "arithmetic exceeds assumption — scalar may be "
                "conservative" if implied - sg > 0.10 else
                "assumption exceeds arithmetic — scalar is not "
                "grounded in stated capacity" if sg - implied > 0.10
                else "assumption consistent with stated capacity")
    return out


_EQUATIONS = {"neocloud": _neocloud}


def evaluate(sym: str, legs: dict) -> Optional[dict]:
    """Run the business-model equation for a symbol, if its module
    has one. Module comes from the sector YAML — curated symbol_map
    wins, same rule as the research layer."""
    try:
        from app.research import sectors
        module = sectors.classify_model(sym, "ai_infra")
    except Exception as exc:
        logger.debug("driver_math classify %s: %s", sym, exc)
        return None
    fn = _EQUATIONS.get(module)
    if not fn:
        return None
    try:
        return fn(sym.upper(), legs)
    except Exception as exc:
        logger.debug("driver_math %s: %s", sym, exc)
        return None
