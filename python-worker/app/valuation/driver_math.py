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


# ------------------------- memory / storage -------------------------
# Revenue = bits shipped × blended ASP. The mix is the lever — HBM
# carries ~5-8× commodity-DRAM revenue per bit, so a mix shift moves
# revenue without a single extra wafer. Equation:
#
#   revenue_fwd = ttm × (1 + bit_growth) × (1 + blended_asp_chg)
#   blended_asp_chg = Σ segment_share_i × asp_chg_i
#
# Segment shares come from driver inputs (dram_share, hbm_share, ...)
# else the labeled mix priors below — declared, never presented as
# segment disclosures.
#
# Mix priors (public segment mixes, late-2026 shapes):
#   MU   ~68% DRAM ex-HBM · ~12% HBM · ~18% NAND
#   WDC  pure HDD post-SNDK spin · STX pure HDD nearline
#   SNDK pure NAND / enterprise-SSD
_SEG_MIX_PRIORS = {
    "MU":   {"dram": 0.68, "hbm": 0.12, "nand": 0.18, "other": 0.02},
    "WDC":  {"hdd": 1.0},
    "STX":  {"hdd": 1.0},
    "SNDK": {"nand": 1.0},
}


def _seg_mix(sym: str, legs: dict) -> tuple[dict, str]:
    """Segment shares — inputs first, labeled priors otherwise."""
    shares = {}
    for seg in ("dram", "hbm", "nand", "hdd"):
        leg = _base(legs, f"{seg}_share")
        if leg and leg.get("value") is not None:
            shares[seg] = leg["value"]
    if shares:
        return shares, "inputs"
    prior = _SEG_MIX_PRIORS.get(sym)
    return (dict(prior) if prior else {}), "mix_prior"


def _memory_compute(sym: str, legs: dict, ttm: Optional[float],
                    overrides: Optional[dict] = None) -> dict:
    """Shared core for evaluate() and scenario(). Overrides carry
    caller-supplied {'asp_chg': {seg: frac}, 'bit_growth': frac} —
    labeled scenario inputs, journaled nowhere."""
    shares, mix_src = _seg_mix(sym, legs)
    ovr = overrides or {}
    if ovr.get("mix"):
        shares = {k: v for k, v in ovr["mix"].items()}
        mix_src = "scenario_override"
    _tot = sum(shares.values())
    if _tot and abs(_tot - 1.0) > 0.05:
        shares = {k: v / _tot for k, v in shares.items()}   # renormalize
    asp = {}
    for seg in shares:
        leg = _base(legs, f"{seg}_asp_chg")
        v = leg["value"] if leg and leg.get("value") is not None else None
        o = (ovr.get("asp_chg") or {}).get(seg)
        if o is not None:
            asp[seg] = {"value": o, "source": "scenario_override"}
        elif v is not None:
            asp[seg] = {"value": v, "source": "input"}
        else:
            asp[seg] = {"value": 0.0, "source": "none_assumed_flat"}
    bit_leg = _base(legs, "bit_growth")
    bit = ovr.get("bit_growth")
    bit_src = "scenario_override"
    if bit is None:
        bit = bit_leg["value"] if bit_leg and \
            bit_leg.get("value") is not None else 0.0
        bit_src = "input" if bit_leg else "none_assumed_flat"

    blended = sum(shares[s] * asp[s]["value"] for s in asp)
    out: dict[str, Any] = {
        "module": "memory_storage",
        "formula": "ttm × (1+bit_growth) × (1+Σ share×asp_chg)",
        "mix": {s: round(v, 3) for s, v in shares.items()},
        "mix_source": mix_src,
        "asp_chg": {s: {"chg": a["value"], "src": a["source"]}
                    for s, a in asp.items()},
        "bit_growth": {"value": bit, "src": bit_src},
        "blended_asp_chg": round(blended, 4),
        "per_seg_contribution": {
            s: round(shares[s] * asp[s]["value"], 4) for s in asp},
    }
    if ttm:
        fwd = ttm * (1 + bit) * (1 + blended)
        out["ttm_revenue"] = round(ttm)
        out["revenue_forward"] = round(fwd)
        out["implied_growth"] = round(fwd / ttm - 1, 3)
    return out


def _memory_storage(sym: str, legs: dict) -> dict:
    ttm = _ttm_revenue(sym)
    out = _memory_compute(sym, legs, ttm)
    standing = _base(legs, "revenue_growth")
    if out.get("implied_growth") is not None and standing and \
            standing.get("value") is not None:
        out["standing_growth"] = standing["value"]
        out["growth_divergence"] = round(
            out["implied_growth"] - standing["value"], 3)
    return out


_EQUATIONS = {"neocloud": _neocloud,
              "memory_storage": _memory_storage}


def scenario(sym: str, overrides: dict) -> Optional[dict]:
    """What-if driver arithmetic — caller supplies
    {'asp_chg': {'dram': .3, 'hbm': .2}, 'bit_growth': .15} and gets
    the implied revenue path per name. Never journaled: scenario
    inputs are the caller's hypothesis, not evidence."""
    try:
        from app.research import sectors
        module = sectors.classify_model(sym, "ai_infra")
    except Exception:
        return None
    if module != "memory_storage":
        return {"error": f"no scenario equation for {module} yet"}
    from app.database import db
    rows = db.execute_query(
        "SELECT DISTINCT ON (driver_key) driver_key, value,"
        " assumption_type, confidence FROM driver_assumptions"
        " WHERE symbol=:s AND scenario='base'"
        " ORDER BY driver_key, as_of DESC", {"s": sym.upper()}) or []
    legs = {r["driver_key"]: {"base": {
        "value": r["value"], "type": r["assumption_type"],
        "confidence": r["confidence"]}} for r in rows}
    out = _memory_compute(sym.upper(), legs, _ttm_revenue(sym.upper()),
                          overrides)
    out["symbol"] = sym.upper()
    out["overrides"] = overrides
    out["scenario_note"] = "unjournaled hypothesis — not evidence"
    return out


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
