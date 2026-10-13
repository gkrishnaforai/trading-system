"""Phase 2 deterministic scorers — durability, AI-capex regime,
cycle warning, shadow demand gate.

All functions are pure: claims/profile in, scores out. Missing
evidence produces `unknown`/exclusion, never a favorable default.
A claim's weight is its confidence; nothing is invented.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import yaml

_POLICY_PATH = os.path.join(os.path.dirname(__file__),
                            "demand_profile.yaml")
_CONF_W = {"high": 1.0, "medium": 0.6, "low": 0.3}
_GROUP_DIR = {"positive": "up", "negative": "down"}


def _policy() -> Dict[str, Any]:
    try:
        with open(_POLICY_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _fresh(c: Dict[str, Any], days: float,
           now: datetime) -> bool:
    sd = c.get("source_date")
    if sd is None:
        return True
    d = sd if isinstance(sd, datetime) else datetime.fromisoformat(
        str(sd).replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (now - d).days <= days


# ── durability score ───────────────────────────────────────────────

def durability_score(profile: Dict[str, Any],
                     evidence: Optional[Dict[str, Any]] = None
                     ) -> Dict[str, Any]:
    """0-100 weighted score over available dimensions. Dimensions
    whose axis is unknown are excluded and the score renormalizes;
    coverage → confidence, never silence."""
    cfg = _policy().get("durability_score") or {}
    dims = cfg.get("dimensions") or {}
    thresh = cfg.get("coverage_thresholds") or {}
    total = sum(float(d.get("weight") or 0) for d in dims.values()) or 1
    got = 0.0
    parts: Dict[str, Any] = {}
    for name, dim in dims.items():
        by = dim.get("by_axis") or {}
        axis = by.get("axis")
        axv = profile.get(axis) if axis else None
        base = (by.get("map") or {}).get(axv) if axv else None
        if base is None:
            continue  # unknown → excluded, renormalized
        score = float(base)
        ev_axis = dim.get("evidence_axis")
        ev = (evidence or {}).get(ev_axis) if ev_axis else None
        if ev:
            shift = float(dim.get("evidence_shift") or 0)
            score += shift * (float(ev.get("pos_score") or 0)
                              - float(ev.get("neg_score") or 0))
        score = max(0.0, min(100.0, score))
        w = float(dim.get("weight") or 0)
        got += w
        parts[name] = {"weight": w, "score": round(score, 1),
                       "axis": axv}
    coverage = got / total
    score_out = round(sum(p["weight"] * p["score"]
                          for p in parts.values()) / got, 1) if got else None
    conf = ("high" if coverage >= float(thresh.get("high", 0.7))
            else "medium" if coverage >= float(thresh.get("medium", 0.45))
            else "low")
    return {"score": score_out, "coverage": round(coverage, 3),
            "confidence": conf if score_out is not None else "unknown",
            "dimensions": parts}


# ── market-level AI capex regime + warning ─────────────────────────

def _group_directions(claims: List[Dict[str, Any]],
                      cfg: Dict[str, Any],
                      now: datetime) -> Dict[str, str]:
    groups = cfg.get("groups") or {}
    fresh = float(cfg.get("freshness_days") or 200)
    out: Dict[str, str] = {}
    for name, spec in groups.items():
        pos = neg = 0.0
        for c in claims:
            if c.get("status") != "approved":
                continue
            if not _fresh(c, fresh, now):
                continue
            sig = c.get("signal")
            w = _CONF_W.get(c.get("confidence") or "medium", 0.6)
            if sig in (spec.get("positive") or []):
                pos += w
            elif sig in (spec.get("negative") or []):
                neg += w
        if pos and neg:
            out[name] = "mixed"
        elif pos:
            out[name] = "up"
        elif neg:
            out[name] = "down"
        else:
            out[name] = "unknown"
    return out


def ai_capex_regime(claims: List[Dict[str, Any]],
                    now: Optional[datetime] = None) -> Dict[str, Any]:
    """Weighted-consensus market regime — never one company's word.
    Moderating spend + rising usage = normalization, not risk."""
    now = now or datetime.now(timezone.utc)
    cfg = _policy().get("ai_regime") or {}
    dirs = _group_directions(claims, cfg, now)
    down = {g for g, d in dirs.items() if d == "down"}
    up = {g for g, d in dirs.items() if d == "up"}
    regime = "unknown"
    for rule in cfg.get("rules") or []:
        w = rule.get("when") or {}
        if len(down) < int(w.get("down_groups_at_least") or 0):
            continue
        if len(up) < int(w.get("up_groups_at_least") or 0):
            continue
        if not set(w.get("must_include") or []) <= down:
            continue
        if not set(w.get("up_must_include") or []) <= up:
            continue
        regime = rule.get("name") or "unknown"
        break
    return {"regime": regime, "groups": dirs,
            "down_groups": sorted(down), "up_groups": sorted(up)}


def cycle_warning_score(claims: List[Dict[str, Any]],
                        now: Optional[datetime] = None) -> Dict[str, Any]:
    """0-100 deterioration score. Requires >=min_escalation_groups
    independent down groups to exceed cap_below_min — one weak
    quarter is noise, not a cycle call."""
    now = now or datetime.now(timezone.utc)
    cfg = _policy().get("cycle_warning") or {}
    dirs = _group_directions(claims,
                             _policy().get("ai_regime") or {}, now)
    weights = cfg.get("group_weights") or {}
    raw = sum(float(weights.get(g) or 0)
              for g, d in dirs.items() if d == "down")
    mixed = sum(float(weights.get(g) or 0) * 0.5
                for g, d in dirs.items() if d == "mixed")
    score = raw + mixed
    n_down = sum(1 for d in dirs.values() if d == "down")
    min_g = int(cfg.get("min_escalation_groups") or 2)
    capped = False
    if n_down < min_g:
        cap = float(cfg.get("cap_below_min") or 30)
        if score > cap:
            score, capped = cap, True
    return {"score": round(min(100.0, score), 1),
            "down_groups": n_down, "capped": capped,
            "groups": dirs}


# ── shadow demand gate ─────────────────────────────────────────────

def demand_gate(profile: Dict[str, Any],
                regime: Optional[Dict[str, Any]] = None,
                durability: Optional[Dict[str, Any]] = None
                ) -> Dict[str, Any]:
    """SHADOW modifier — evaluated, persisted, never applied to the
    action until shadow comparison validates it. First rule wins."""
    cfg = _policy().get("demand_gate") or {}
    reg = (regime or {}).get("regime") or "unknown"
    funding = profile.get("capital_funding_risk") or "unknown"
    sens = profile.get("capex_sensitivity") or "unknown"
    dur = profile.get("demand_durability") or "unknown"
    util = profile.get("utilization_health") or "unknown"

    gate, reasons = "permit_add", []
    for rule in cfg.get("rules") or []:
        w = rule.get("when") or {}
        if w.get("funding_in") and funding not in w["funding_in"]:
            continue
        if w.get("sensitivity_in") and sens not in w["sensitivity_in"]:
            continue
        if w.get("durability_in") and dur not in w["durability_in"]:
            continue
        if w.get("utilization_in") and util not in w["utilization_in"]:
            continue
        if w.get("regime_in") and reg not in w["regime_in"]:
            continue
        gate = rule.get("gate") or "permit_add"
        reasons = [k for k in w]
        break

    req = cfg.get("long_term_requires") or {}
    lt_ok = (dur in (req.get("durability_in") or [])
             and funding not in (req.get("funding_not_in") or [])
             and (not req.get("no_conflicts")
                  or not (profile.get("conflicts"))))
    return {"gate": gate, "matched_on": reasons,
            "long_term_eligible": lt_ok,
            "regime": reg,
            "durability_score": (durability or {}).get("score"),
            "shadow": True}


# ── scenario stress fields ─────────────────────────────────────────

def demand_scenarios(profile: Dict[str, Any],
                     scalars: Dict[str, Any]) -> Dict[str, Any]:
    """Three-scenario revenue/margin stress. Base growth is MEASURED
    (forward vs TTM revenue); scenario growth = base × model shock.
    Anything not responsibly estimable stays unknown."""
    shocks = (_policy().get("model_growth_shock") or {})
    model = profile.get("demand_model") or "unknown"
    shock = shocks.get(model) or shocks.get("unknown") or {}
    rt, rf = scalars.get("revenue_ttm"), scalars.get("revenue_forward")
    base_g = None
    try:
        if rt and rf and float(rt) > 0:
            base_g = float(rf) / float(rt) - 1.0
    except (TypeError, ValueError):
        base_g = None
    out = {
        "revenue_growth_base": (round(base_g, 4)
                                if base_g is not None else "unknown"),
        "revenue_growth_slowdown": (round(base_g * float(
            shock.get("slowdown", 0.75)), 4)
            if base_g is not None else "unknown"),
        "revenue_growth_stress": (round(base_g * float(
            shock.get("stress", 0.5)), 4)
            if base_g is not None else "unknown"),
        "fcf_stress_state": (profile.get("capital_funding_risk")
                             or "unknown"),
    }
    breaks = []
    if profile.get("capex_sensitivity") in ("very_high", "high"):
        breaks.append("customer capex orders/guide down 2+ groups")
    if profile.get("demand_durability") in ("discretionary",
                                            "speculative"):
        breaks.append("contract/backlog claims cancel or stall")
    if profile.get("capital_funding_risk") in ("high", "critical"):
        breaks.append("refinancing unavailable at acceptable cost")
    if profile.get("utilization_health") == "falling":
        breaks.append("utilization deterioration confirmed")
    if not breaks:
        breaks.append("no model-specific break conditions identified")
    out["thesis_break_conditions"] = breaks
    return out
