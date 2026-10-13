"""Decision layer — fair value → buy price.

The engine's scenarios price what the business is worth; this layer
converts that into what it's safe to pay: probability-weighted value
minus a category-and-uncertainty margin of safety, horizon return,
confidence roll, and downside gates. Deterministic policy from
mos_policy.yaml — no judgment calls in the math.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

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


def _mos_base_for(cats: Dict[str, Any],
                  archetypes: List[str],
                  default_base: float) -> float:
    """Strictest applicable base across the matched archetype set — a
    name that is partly ai_infra shouldn't earn the cheaper technology
    discount. Single-archetype names reduce to their category base."""
    base = default_base
    for a in archetypes or []:
        spec = cats.get(a)
        if spec is not None:
            base = max(base, float(spec.get("base", default_base)))
    return base


def _macro_scenarios(scen_cfg: Dict[str, Any],
                     archetypes: List[str],
                     fv_ref: Optional[float],
                     buy_below: Optional[float],
                     spot: Optional[float]) -> Dict[str, Any]:
    """Stress overlay: expected FV and buy_below re-priced under each
    AI-capex macro scenario. Primary archetype carries weight
    1 - secondary_blend; matched secondaries share the rest."""
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
        impact = ((1 - blend_w) * p +
                  (blend_w * sum(secs) / len(secs) if secs else 0))
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
           archetypes: Optional[List[str]] = None) -> Dict[str, Any]:
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
    base = _mos_base_for(cats, archs,
                         float(policy.get("default_base", 0.25)))

    # uncertainty adders — each a measurable risk the scenario may miss
    applied: List[str] = []
    mos = base
    fcf = scalars.get("fcf_ttm")
    try:
        if fcf is not None and float(fcf) <= 0:
            mos += adders.get("negative_fcf", 0); applied.append("negative_fcf")
    except (TypeError, ValueError):
        pass
    try:
        if float(scalars.get("total_debt") or 0) > \
                2 * float(scalars.get("cash_and_equivalents") or 0) \
                and float(scalars.get("total_debt") or 0) > 0:
            mos += adders.get("high_leverage", 0); applied.append("high_leverage")
    except (TypeError, ValueError):
        pass
    for flag, key in (("scenarios_partial", "scenarios_partial"),
                      ("no_scenarios", "no_scenarios"),
                      ("extreme_gap", "extreme_gap")):
        if flag in (quality_flags or []):
            mos += adders.get(key, 0); applied.append(flag)
    if scalars.get("analyst_count") in (None, 0):
        mos += adders.get("no_analyst_coverage", 0)
        applied.append("no_analyst_coverage")
    mos = round(min(mos, cap), 4)

    fv_ref = expected_fv or fair_value
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

    # confidence roll — policy thresholds over flags + method coverage
    ok_n = len([m for m in (method_results or [])
                if getattr(m, "status", None) == "ok"
                or (isinstance(m, dict) and m.get("status") == "ok")])
    hi = (policy.get("confidence") or {}).get("high_needs") or {}
    me = (policy.get("confidence") or {}).get("medium_needs") or {}
    def _ok_for(spec):
        return ok_n >= int(spec.get("min_ok_methods", 99)) and not any(
            f in (quality_flags or []) for f in spec.get("forbid_flags", []))
    confidence = ("high" if fv_ref and _ok_for(hi)
                  else "medium" if fv_ref and _ok_for(me)
                  else "low")

    return {
        "mos_pct": mos,
        "mos_base": base,
        "mos_adders": applied,
        "buy_below": buy_below,
        "fv_upside_pct": upside,
        "expected_return_2y": er2y,
        "valuation_confidence": confidence,
        "risk_flags": risk_flags,
        "fv_reference": "expected" if expected_fv else "base",
        "macro_scenarios": _macro_scenarios(
            scen_cfg, archs, fv_ref, buy_below, spot),
    }
