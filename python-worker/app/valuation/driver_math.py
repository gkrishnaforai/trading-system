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


# ---------------------- project / backlog models --------------------
# Power delivery, thermal, grid-equipment: revenue is backlog shipped
# + a service annuity + in-year book-and-turn. Equation:
#
#   rev_fwd = backlog × conv_rate
#           + ttm × service_share × (1+service_growth)
#           + ttm × in_year_share
#
# conv_rate is the annual ship-through of the standing backlog; the
# in-year leg is orders that book AND turn inside the year — the piece
# book_to_bill>1 feeds but can't be assumed into existence.
_PROJ_PRIORS = {"conv_rate": 0.50, "service_share": 0.20,
                "service_growth": 0.08, "in_year_share": 0.35}


def _project_compute(sym: str, legs: dict, ttm: Optional[float],
                     overrides: Optional[dict] = None) -> dict:
    ovr = overrides or {}
    inputs: dict[str, dict] = {}
    missing: list[str] = []
    for key in ("backlog", "conv_rate", "service_share",
                "service_growth", "in_year_share", "book_to_bill"):
        leg = _base(legs, key)
        o = ovr.get(key)
        if o is not None:
            inputs[key] = {"value": o, "source": "scenario_override"}
        elif leg and leg.get("value") is not None:
            inputs[key] = {"value": leg["value"], "source": "input",
                           "type": leg["type"],
                           "confidence": leg.get("confidence")}
        elif key in _PROJ_PRIORS:
            inputs[key] = {"value": _PROJ_PRIORS[key],
                           "source": "model_prior"}
        else:
            missing.append(key)

    def _v(k):
        return (inputs.get(k) or {}).get("value")

    conv = _v("conv_rate")
    out: dict[str, Any] = {
        "module": "project_backlog",
        "formula": "backlog×conv + ttm×service_share×(1+g) "
                   "+ ttm×in_year_share",
        "inputs": inputs, "missing": missing,
    }
    backlog = _v("backlog")
    if ttm:
        parts = {}
        if backlog is not None and conv is not None:
            parts["backlog_shipped"] = backlog * conv
        ss, sg, iy = _v("service_share"), _v("service_growth"), \
            _v("in_year_share")
        if ss is not None:
            parts["service"] = ttm * ss * (1 + (sg or 0.0))
        if iy is not None:
            parts["in_year_book_and_turn"] = ttm * iy
        if parts:
            fwd = sum(parts.values())
            out["components"] = {k: round(v) for k, v in parts.items()}
            out["ttm_revenue"] = round(ttm)
            # implied growth is only honest when the demand leg ran —
            # a service-only number isn't a forecast, it's coverage
            if backlog is not None:
                out["revenue_forward"] = round(fwd)
                out["implied_growth"] = round(fwd / ttm - 1, 3)
            else:
                out["revenue_partial"] = round(fwd)
                out["coverage_note"] = "service+in-year only — no backlog"
            btb = _v("book_to_bill")
            if btb is not None:
                out["book_to_bill"] = btb
                out["trajectory"] = (
                    "backlog building — forward coverage improving"
                    if btb > 1.05 else
                    "backlog draining — shipping faster than booking"
                    if btb < 0.95 else "book-to-bill ~1: steady state")
    if backlog is None:
        out["note"] = ("no backlog input — the equation's biggest "
                       "term can't run; journal a commitment or "
                       "pass a scenario override")
    return out


def _project_backlog(sym: str, legs: dict) -> dict:
    ttm = _ttm_revenue(sym)
    out = _project_compute(sym, legs, ttm)
    standing = _base(legs, "revenue_growth")
    if out.get("implied_growth") is not None and standing and \
            standing.get("value") is not None:
        out["standing_growth"] = standing["value"]
        out["growth_divergence"] = round(
            out["implied_growth"] - standing["value"], 3)
    return out


# --------- mix-growth models (server_oem, optical_photonics) ---------
# One hot AI segment on a slower base. Revenue is the blend:
#
#   rev_fwd = hot_rev + ttm × (1−hot_share) × (1+other_g)
#   hot_rev resolves deep when granular drivers exist:
#     server_oem:         rack_units × rev_per_rack
#     optical_photonics:  ports_{gen} × asp_{gen}, summed over gens
#   else:                 ttm × hot_share × (1+hot_g)
#
# The equation's job is separating the AI ramp from the legacy base —
# a DELL growing servers 5% and AI 60% is not the same name as one
# growing everything 20%.
_MIX_CFG = {
    "server_oem":         {"hot": "ai_server", "hot_share": 0.25,
                           "hot_g": 0.50, "other_g": 0.02,
                           "units": ["rack_units"],
                           "price": ["rev_per_rack"]},
    "optical_photonics":  {"hot": "ai_datacom", "hot_share": 0.55,
                           "hot_g": 0.45, "other_g": 0.03,
                           "units": ["ports_800g", "ports_1p6t"],
                           "price": ["asp_800g", "asp_1p6t"]},
}


def _mix_growth_compute(sym: str, legs: dict, ttm: Optional[float],
                        overrides: Optional[dict],
                        kind: str) -> dict:
    cfg = _MIX_CFG[kind]
    hot = cfg["hot"]
    ovr = overrides or {}
    inputs: dict[str, dict] = {}
    missing: list[str] = []
    keys = [f"{hot}_share", f"{hot}_g", "other_g",
            *cfg["units"], *cfg["price"]]
    for key in keys:
        leg = _base(legs, key)
        o = ovr.get(key)
        if o is not None:
            inputs[key] = {"value": o, "source": "scenario_override"}
        elif leg and leg.get("value") is not None:
            inputs[key] = {"value": leg["value"], "source": "input",
                           "type": leg["type"],
                           "confidence": leg.get("confidence")}
        else:
            missing.append(key)

    def _v(k, prior=None):
        return (inputs.get(k) or {}).get("value", prior)

    share = _v(f"{hot}_share", cfg["hot_share"])
    share_src = (inputs.get(f"{hot}_share") or {}).get(
        "source", "model_prior")
    hot_g = _v(f"{hot}_g", cfg["hot_g"])
    other_g = _v("other_g", cfg["other_g"])

    out: dict[str, Any] = {
        "module": kind,
        "formula": f"{hot}_rev + ttm×(1−{hot}_share)×(1+other_g)",
        "inputs": inputs, "missing": missing,
        f"{hot}_share": {"value": share, "source": share_src},
    }
    if not ttm:
        out["note"] = "no TTM revenue — equation can't run"
        return out

    # deep path — granular units × price when those inputs exist
    deep = None
    uvs = [_v(u) for u in cfg["units"]]
    pvs = [_v(p) for p in cfg["price"]]
    if len(cfg["units"]) == 1 and uvs[0] and pvs[0]:
        deep = uvs[0] * pvs[0]
    elif len(cfg["units"]) > 1 and all(uvs) and all(pvs):
        deep = sum(u * p for u, p in zip(uvs, pvs))
    if deep is not None:
        hot_rev = deep
        hot_src = "units_x_price"
    else:
        hot_rev = ttm * share * (1 + hot_g)
        hot_src = "share_x_growth"

    other_rev = ttm * (1 - share) * (1 + other_g)
    fwd = hot_rev + other_rev
    out.update({
        f"{hot}_revenue_fwd": round(hot_rev),
        "hot_revenue_source": hot_src,
        "other_revenue_fwd": round(other_rev),
        "ttm_revenue": round(ttm),
        "revenue_forward": round(fwd),
        "implied_growth": round(fwd / ttm - 1, 3),
        "hot_share_fwd": round(hot_rev / fwd, 3),
    })
    return out


def _server_oem(sym: str, legs: dict) -> dict:
    out = _mix_growth_compute(sym, legs, _ttm_revenue(sym), None,
                              "server_oem")
    standing = _base(legs, "revenue_growth")
    if out.get("implied_growth") is not None and standing and \
            standing.get("value") is not None:
        out["standing_growth"] = standing["value"]
        out["growth_divergence"] = round(
            out["implied_growth"] - standing["value"], 3)
    return out


def _optical(sym: str, legs: dict) -> dict:
    out = _mix_growth_compute(sym, legs, _ttm_revenue(sym), None,
                              "optical_photonics")
    standing = _base(legs, "revenue_growth")
    if out.get("implied_growth") is not None and standing and \
            standing.get("value") is not None:
        out["standing_growth"] = standing["value"]
        out["growth_divergence"] = round(
            out["implied_growth"] - standing["value"], 3)
    return out


# ------------------------- semicap_equipment --------------------------
# WFE suppliers book orders quarters ahead of shipment; a service
# annuity rides the installed base between cycles:
#
#   rev_fwd = orders_annualized × ship_conv
#           + ttm × service_share × (1+service_growth)
#
# deep path when market inputs exist: rev_fwd = wfe_market × share —
# the two should roughly agree; divergence is itself the signal.
_SEMI_PRIORS = {"ship_conv": 0.95, "service_share": 0.28,
                "service_growth": 0.07}


def _semicap_compute(sym: str, legs: dict, ttm: Optional[float],
                     overrides: Optional[dict] = None) -> dict:
    ovr = overrides or {}
    inputs: dict[str, dict] = {}
    missing: list[str] = []
    for key in ("orders_intake", "ship_conv", "service_share",
                "service_growth", "book_to_bill",
                "wfe_market", "wfe_share"):
        leg = _base(legs, key)
        o = ovr.get(key)
        if o is not None:
            inputs[key] = {"value": o, "source": "scenario_override"}
        elif leg and leg.get("value") is not None:
            inputs[key] = {"value": leg["value"], "source": "input",
                           "type": leg["type"],
                           "confidence": leg.get("confidence")}
        elif key in _SEMI_PRIORS:
            inputs[key] = {"value": _SEMI_PRIORS[key],
                           "source": "model_prior"}
        else:
            missing.append(key)

    def _v(k):
        return (inputs.get(k) or {}).get("value")

    out: dict[str, Any] = {
        "module": "semicap_equipment",
        "formula": "orders×ship_conv + ttm×service_share×(1+g)"
                   "   [deep: wfe×share]",
        "inputs": inputs, "missing": missing,
    }
    orders, conv = _v("orders_intake"), _v("ship_conv")
    wfe, share = _v("wfe_market"), _v("wfe_share")
    ss, sg = _v("service_share"), _v("service_growth")
    if ttm:
        parts = {}
        if orders is not None and conv is not None:
            parts["orders_shipped"] = orders * conv
        if ss is not None:
            parts["service"] = ttm * ss * (1 + (sg or 0.0))
        if parts:
            fwd = sum(parts.values())
            out["components"] = {k: round(v) for k, v in parts.items()}
            out["ttm_revenue"] = round(ttm)
            # orders leg missing → parts is service-only coverage,
            # not a forecast
            if orders is not None:
                out["revenue_forward"] = round(fwd)
                out["implied_growth"] = round(fwd / ttm - 1, 3)
            else:
                out["revenue_partial"] = round(fwd)
                out["coverage_note"] = "service annuity only — no orders"
        if wfe is not None and share is not None:
            out["wfe_path"] = {
                "revenue_forward": round(wfe * share),
                "implied_growth": round(wfe * share / ttm - 1, 3),
                "note": "market-share path — compare vs orders path"}
        btb = _v("book_to_bill")
        if btb is not None:
            out["book_to_bill"] = btb
            out["trajectory"] = (
                "orders outpacing shipments — cycle building"
                if btb > 1.05 else
                "orders lagging shipments — cycle draining"
                if btb < 0.95 else "book-to-bill ~1: steady state")
    if orders is None:
        out["note"] = ("no orders_intake — the demand leg can't run; "
                       "journal a bookings commitment or pass an "
                       "override")
    return out


def _semicap(sym: str, legs: dict) -> dict:
    out = _semicap_compute(sym, legs, _ttm_revenue(sym))
    standing = _base(legs, "revenue_growth")
    if out.get("implied_growth") is not None and standing and \
            standing.get("value") is not None:
        out["standing_growth"] = standing["value"]
        out["growth_divergence"] = round(
            out["implied_growth"] - standing["value"], 3)
    return out


_EQUATIONS = {"neocloud": _neocloud,
              "memory_storage": _memory_storage,
              "power_delivery": _project_backlog,
              "thermal_cooling": _project_backlog,
              "server_oem": _server_oem,
              "optical_photonics": _optical,
              "semicap_equipment": _semicap}

# module → core compute fn for the scenario layer
_SCENARIO_FNS = {
    "memory_storage": _memory_compute,
    "power_delivery": _project_compute,
    "thermal_cooling": _project_compute,
    "semicap_equipment": _semicap_compute,
    "server_oem": lambda s, l, t, o: _mix_growth_compute(
        s, l, t, o, "server_oem"),
    "optical_photonics": lambda s, l, t, o: _mix_growth_compute(
        s, l, t, o, "optical_photonics"),
}


def scenario(sym: str, overrides: dict) -> Optional[dict]:
    """What-if driver arithmetic — caller supplies
    {'asp_chg': {'dram': .3, 'hbm': .2}, 'bit_growth': .15} and gets
    the implied revenue path per name. Never journaled: scenario
    inputs are the caller's hypothesis, not evidence."""
    module = _module_of(sym)
    fn = _SCENARIO_FNS.get(module) if module else None
    if not fn:
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
    out = fn(sym.upper(), legs, _ttm_revenue(sym.upper()), overrides)
    out["module"] = module
    out["symbol"] = sym.upper()
    out["overrides"] = overrides
    out["scenario_note"] = "unjournaled hypothesis — not evidence"
    return out


_SECTORS = ("ai_infra", "healthcare", "generic")


def _module_of(sym: str) -> Optional[str]:
    """Sector-generic module lookup — try every sector config; the
    curated symbol_map wins wherever the name was mapped."""
    from app.research import sectors
    for sec in _SECTORS:
        try:
            m = sectors.classify_model(sym, sec)
            if m and m != "unclassified":
                return m
        except Exception:
            continue
    return None


def evaluate(sym: str, legs: dict) -> Optional[dict]:
    """Run the business-model equation for a symbol, if its module
    has one. Module comes from the sector YAML — curated symbol_map
    wins, same rule as the research layer."""
    module = _module_of(sym)
    fn = _EQUATIONS.get(module) if module else None
    if not fn:
        return None
    try:
        return fn(sym.upper(), legs)
    except Exception as exc:
        logger.debug("driver_math %s: %s", sym, exc)
        return None
