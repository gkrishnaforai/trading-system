"""Business-demand exposure layer — how a company earns its next
dollar and what happens if AI capex slows.

Separate questions, kept separate:
  demand risk  — will customers keep buying?  (priors → evidence)
  funding risk — can the company deliver?     (measured, always)

Axes are persisted canonical classifications with provenance —
priors from archetype/symbol seeds, upgraded by evidence or human
override, never silently re-inferred per page.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import yaml

_POLICY_PATH = os.path.join(os.path.dirname(__file__),
                            "demand_profile.yaml")

_VALID = {
    "demand_model": {"capex_project", "capacity_rental",
                     "usage_consumption", "recurring_software",
                     "maintenance_services", "power_generation",
                     "replacement_cycle", "mixed", "speculative",
                     "unknown"},
    "capex_sensitivity": {"very_high", "high", "medium", "low",
                          "unknown"},
    "demand_durability": {"contracted", "recurring", "usage_based",
                          "replacement_cycle", "discretionary",
                          "speculative", "unknown"},
    "utilization_health": {"rising", "stable_high", "stable",
                           "falling", "unknown"},
    "capital_funding_risk": {"low", "moderate", "high", "critical",
                             "unknown"},
    "ai_monetization": {"proven", "scaling", "early", "unproven",
                        "unknown"},
}


def _policy() -> Dict[str, Any]:
    try:
        with open(_POLICY_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _funding_risk(cfg: Dict[str, Any], scalars: Dict[str, Any]
                  ) -> str:
    """Measured, not inferred: FCF sign + debt:cash leverage."""
    fcf = scalars.get("fcf_ttm")
    debt = scalars.get("total_debt")
    cash = scalars.get("cash_and_equivalents")
    if fcf is None and (debt is None or cash is None):
        return "unknown"
    rules = ((cfg.get("funding_risk") or {}).get("rules")) or []
    try:
        fcf_neg = fcf is not None and float(fcf) <= 0
        dtc = (float(debt) / float(cash)
               if debt is not None and cash not in (None, 0)
               else None)
        for r in rules:
            w = r.get("when") or {}
            if "fcf_lte" in w:
                if fcf is None or float(fcf) > float(w["fcf_lte"]):
                    continue
            if "debt_to_cash_gt" in w:
                if dtc is None or dtc <= float(w["debt_to_cash_gt"]):
                    continue
            return str(r.get("level") or "unknown")
    except (TypeError, ValueError):
        return "unknown"
    return str((cfg.get("funding_risk") or {}).get("default") or "low")


def build_profile(symbol: str,
                  archetypes: List[str],
                  scalars: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic exposure profile.

    Axes from evidence-graded priors: a symbol_seed (curated revenue-
    model hypothesis) beats the archetype prior; funding risk is always
    computed from measured inputs. Axes with no evidence stay
    'unknown' — never fabricated.
    """
    cfg = _policy()
    primary = (archetypes or [None])[0]
    prior = (cfg.get("archetype_priors") or {}).get(primary) or {}
    seed = (cfg.get("symbol_priors") or {}).get(
        (symbol or "").upper()) or {}

    def _axis(name: str) -> str:
        v = seed.get(name) or prior.get(name) or "unknown"
        return v if v in _VALID[name] else "unknown"

    model = _axis("demand_model")
    profile = {
        "demand_model": model,
        "capex_sensitivity": _axis("capex_sensitivity"),
        "demand_durability": (cfg.get("durability_by_model") or {})
                             .get(model, "unknown"),
        # utilization needs contract/telemetry data we don't ingest —
        # honest unknown until that evidence exists
        "utilization_health": "unknown",
        "capital_funding_risk": _funding_risk(cfg, scalars),
        "ai_monetization": _axis("ai_monetization"),
    }
    profile["source"] = "symbol_seed" if seed else "archetype_prior"
    profile["impact_mult"] = float(
        (cfg.get("demand_model_impact_mult") or {}).get(model, 1.0))
    return profile
