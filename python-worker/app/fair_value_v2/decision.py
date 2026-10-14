"""Decision layer — fair value → buy price.

The engine's scenarios price what the business is worth; this layer
converts that into what it's safe to pay: probability-weighted value
minus a category-and-uncertainty margin of safety, horizon return,
confidence roll, and downside gates. Deterministic policy from
mos_policy.yaml — no judgment calls in the math.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import yaml

_POLICY_PATH = os.path.join(os.path.dirname(__file__), "mos_policy.yaml")
_SCEN_PATH = os.path.join(os.path.dirname(__file__),
                          "archetype_scenarios.yaml")


def _load_policy() -> Dict[str, Any]:
    try:
        with open(_POLICY_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _load_scenarios() -> Dict[str, Any]:
    try:
        with open(_SCEN_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _mos_range_for(cats: Dict[str, Any],
                   archetypes: List[str],
                   default_low: float,
                   default_high: float) -> Tuple[float, float]:
    """Strictest applicable MoS band across the matched archetype set —
    a name that is partly ai_infra can't hide behind the cheaper
    technology band. Defaults apply only when no category matched;
    {base: x} entries treated as a point range."""
    lo, hi = None, None
    for a in archetypes or []:
        spec = cats.get(a)
        if spec is None:
            continue
        if "low" in spec or "high" in spec:
            l = float(spec.get("low", default_low))
            h = float(spec.get("high", default_high))
        elif "base" in spec:
            l = h = float(spec["base"])
        else:
            continue
        lo = l if lo is None else max(lo, l)
        hi = h if hi is None else max(hi, h)
    if lo is None:
        return default_low, default_high
    return lo, max(lo, hi)


def _macro_scenarios(scen_cfg: Dict[str, Any],
                     archetypes: List[str],
                     fv_ref: Optional[float],
                     buy_below: Optional[float],
                     spot: Optional[float],
                     impact_mult: float = 1.0) -> Dict[str, Any]:
    """Stress overlay: expected FV and buy_below re-priced under each
    AI-capex macro scenario. Primary archetype carries weight
    1 - secondary_blend; matched secondaries share the rest.
    impact_mult modulates by demand model — capacity_rental (NBIS)
    absorbs a capex slowdown better than capex_project (CRDO)."""
    if not fv_ref or not archetypes:
        return {}
    sens = scen_cfg.get("sensitivities") or {}
    blend_w = float(scen_cfg.get("secondary_blend", 0.3))
    primary, secondaries = archetypes[0], archetypes[1:]

    out: Dict[str, Any] = {}
    for key, spec in (scen_cfg.get("scenarios") or {}).items():
        p = float((sens.get(primary) or {}).get(key) or
                  (sens.get("unknown") or {}).get(key) or 0)
        secs = [float((sens.get(s) or {}).get(key) or 0)
                for s in secondaries]
        impact = (((1 - blend_w) * p +
                   (blend_w * sum(secs) / len(secs) if secs else 0))
                  * float(impact_mult or 1.0))
        entry = {"impact": round(impact, 4), "label": spec.get("label")}
        stressed_fv = fv_ref * (1 + impact)
        entry["stressed_fv"] = round(stressed_fv, 2)
        if buy_below:
            entry["stressed_buy_below"] = round(buy_below * (1 + impact), 2)
        if spot and spot > 0:
            entry["stressed_vs_spot"] = round(stressed_fv / spot - 1, 4)
        out[key] = entry
    if out:
        worst = min(out.items(), key=lambda kv: kv[1]["impact"])
        out["_worst"] = {"scenario": worst[0],
                         "impact": worst[1]["impact"],
                         "label": worst[1].get("label")}
    return out


def _scalars_from_methods(method_results: list) -> Dict[str, Any]:
    """Union of every method's inputs_used — the raw features the run
    actually saw (fcf_ttm, total_debt, analyst_count, …)."""
    out: Dict[str, Any] = {}
    for mr in method_results or []:
        iu = getattr(mr, "inputs_used", None) or \
            (mr.get("inputs_used") if isinstance(mr, dict) else None) or {}
        for k, v in iu.items():
            if v is not None and k not in out:
                out[k] = v
    return out


def decide(category: Optional[str],
           fair_value: Optional[float],
           expected_fv: Optional[float],
           scenarios: Dict[str, Any],
           quality_flags: List[str],
           spot: Optional[float],
           method_results: list,
           archetypes: Optional[List[str]] = None,
           demand: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return the decision payload for one run.

    fv_* fields describe worth; buy_below is the gate. risk_flags are
    the blockers/penalties a consumer must respect. `archetypes` is the
    full matched classification set — its strictest member sets the
    margin-of-safety base and its blend sets scenario sensitivities."""
    policy = _load_policy()
    scen_cfg = _load_scenarios()
    cats = policy.get("categories") or {}
    adders = policy.get("adders") or {}
    cap = float(policy.get("cap", 0.60))
    gates = policy.get("gates") or {}

    scalars = _scalars_from_methods(method_results)
    cat = (category or "unknown").split(":")[0] or "unknown"
    archs = list(archetypes) if archetypes else [cat]
    if cat not in archs:
        archs.insert(0, cat)
    low, high = _mos_range_for(
        cats, archs,
        float(policy.get("default_low", 0.20)),
        float(policy.get("default_high", 0.35)))

    fv_ref = expected_fv or fair_value

    # ensemble dispersion — when ok methods disagree on the base FV by a
    # wide share of spot, the blend is pretending precision it lacks;
    # cap confidence and price the disagreement as uncertainty
    disp_cfg = policy.get("dispersion") or {}
    _bases: List[float] = []
    for mr in method_results or []:
        _ok = getattr(mr, "status", None) == "ok" or \
            (isinstance(mr, dict) and mr.get("status") == "ok")
        if not _ok:
            continue
        _fp = getattr(mr, "fair_price", None)
        if _fp is None and isinstance(mr, dict):
            _fp = mr.get("fair_price")
        try:
            if _fp is not None and float(_fp) > 0:
                _bases.append(float(_fp))
        except (TypeError, ValueError):
            pass
    method_dispersion = None
    if len(_bases) >= 2 and spot and float(spot) > 0:
        method_dispersion = round(
            (max(_bases) - min(_bases)) / float(spot), 4)

    # confidence roll first — it positions the MoS within the band
    ok_n = len([m for m in (method_results or [])
                if getattr(m, "status", None) == "ok"
                or (isinstance(m, dict) and m.get("status") == "ok")])
    hi_spec = (policy.get("confidence") or {}).get("high_needs") or {}
    me_spec = (policy.get("confidence") or {}).get("medium_needs") or {}
    def _ok_for(spec):
        return ok_n >= int(spec.get("min_ok_methods", 99)) and not any(
            f in (quality_flags or []) for f in spec.get("forbid_flags", []))
    confidence = ("high" if fv_ref and _ok_for(hi_spec)
                  else "medium" if fv_ref and _ok_for(me_spec)
                  else "low")
    if method_dispersion is not None:
        if method_dispersion > float(disp_cfg.get("medium_conf_max", 0.70)):
            confidence = "low"
        elif method_dispersion > float(disp_cfg.get("high_conf_max", 0.35)) \
                and confidence == "high":
            confidence = "medium"

    # uncertainty adders — each a measurable risk the scenario may miss;
    # their total positions the name inside its category band
    applied: List[str] = []
    adders_total = 0.0
    fcf = scalars.get("fcf_ttm")
    try:
        if fcf is not None and float(fcf) <= 0:
            adders_total += adders.get("negative_fcf", 0)
            applied.append("negative_fcf")
    except (TypeError, ValueError):
        pass
    try:
        if float(scalars.get("total_debt") or 0) > \
                2 * float(scalars.get("cash_and_equivalents") or 0) \
                and float(scalars.get("total_debt") or 0) > 0:
            adders_total += adders.get("high_leverage", 0)
            applied.append("high_leverage")
    except (TypeError, ValueError):
        pass
    for flag, key in (("scenarios_partial", "scenarios_partial"),
                      ("no_scenarios", "no_scenarios"),
                      ("extreme_gap", "extreme_gap")):
        if flag in (quality_flags or []):
            adders_total += adders.get(key, 0); applied.append(flag)
    if scalars.get("analyst_count") in (None, 0):
        adders_total += adders.get("no_analyst_coverage", 0)
        applied.append("no_analyst_coverage")
    # funding risk is a first-class axis — a name can hold demand
    # through a capex slowdown and still be unable to finance delivery
    fr = (demand or {}).get("capital_funding_risk")
    if fr in ("critical", "high"):
        adders_total += adders.get("capital_funding_risk", 0)
        applied.append(f"funding_{fr}")
    if method_dispersion is not None and method_dispersion > \
            float(disp_cfg.get("adder_trigger", 0.50)):
        adders_total += adders.get("method_dispersion", 0)
        applied.append("method_dispersion")
    try:
        _do = scalars.get("dilution_overhang")
        if _do is not None and float(_do) - 1 > 0.05:
            adders_total += adders.get("share_dilution", 0)
            applied.append("share_dilution")
    except (TypeError, ValueError):
        pass
    try:
        _cc = scalars.get("cash_conversion")
        if _cc is not None and float(scalars.get("net_income_ttm") or 0) > 0 \
                and float(_cc) < 0.6:
            adders_total += adders.get("weak_cash_conversion", 0)
            applied.append("weak_cash_conversion")
    except (TypeError, ValueError):
        pass

    score = min(1.0, adders_total /
                float(policy.get("range_scale", 0.25) or 0.25))
    if confidence == "high":
        score *= float(policy.get("high_confidence_dampen", 0.6))
    elif confidence == "low":
        score = max(score, float(policy.get("low_confidence_floor", 0.5)))
    mos = round(min(low + (high - low) * score, cap), 4)

    buy_below = round(fv_ref * (1 - mos), 4) if fv_ref else None

    upside = None
    er2y = None
    risk_flags: List[str] = []
    if spot and spot > 0 and fv_ref:
        upside = round(fv_ref / spot - 1, 4)
    base_fv = (scenarios or {}).get("base") or fv_ref
    if spot and spot > 0 and base_fv and base_fv > 0:
        er2y = round((base_fv / spot) ** 0.5 - 1, 4)
    bear = (scenarios or {}).get("bear")
    if spot and spot > 0 and bear is not None:
        bear_down = bear / spot - 1
        if bear_down < float(gates.get("bear_loss_severe", -0.40)):
            risk_flags.append("bear_loss_severe")
    if mos >= float(gates.get("uninvestable_mos", 0.60)):
        risk_flags.append("uninvestable_mos")
    if fv_ref is None:
        risk_flags.append("no_fair_value")

    return {
        "mos_pct": mos,
        "mos_band": [low, high],
        "mos_adders": applied,
        "buy_below": buy_below,
        "fv_upside_pct": upside,
        "expected_return_2y": er2y,
        "valuation_confidence": confidence,
        "method_dispersion": method_dispersion,
        "risk_flags": risk_flags,
        "fv_reference": "expected" if expected_fv else "base",
        "spot": spot,
        "demand_profile": demand,
        "macro_scenarios": _macro_scenarios(
            scen_cfg, archs, fv_ref, buy_below, spot,
            impact_mult=(demand or {}).get("impact_mult", 1.0)),
    }
