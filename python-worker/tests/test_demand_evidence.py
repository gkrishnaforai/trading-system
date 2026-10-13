"""Demand-layer regression tests — the framework cases that are
implementable before Phase 2 regime detection:

  - missing utilization stays unknown (never promoted)
  - conflicting sources → conflict preserved, confidence lowered
  - approved evidence upgrades axes per signal_map
  - funding risk measured from inputs; evidence escalates only
  - stale evidence ignored for axes, kept for audit
  - demand_model can be reclassified by filing evidence (value payload)
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.fair_value_v2.demand import build_profile  # noqa: E402
from app.fair_value_v2.demand_evidence import (  # noqa: E402
    derive_axes, validate_claim)

NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(days=30)).isoformat()
STALE = (NOW - timedelta(days=400)).isoformat()


def _claim(axis, signal, **kw):
    base = {"symbol": "TEST", "axis": axis, "signal": signal,
            "claim": "fact", "source": "filing",
            "source_date": RECENT, "confidence": "high",
            "status": "approved"}
    base.update(kw)
    return base


# ── framework cases ────────────────────────────────────────────────

def test_missing_utilization_stays_unknown():
    p = build_profile("TEST", ["ai_infra"], {})
    assert p["utilization_health"] == "unknown"
    assert p["evidence_confidence"] == "unknown"


def test_conflicting_guidance_preserves_conflict():
    claims = [
        _claim("demand_durability", "contract_signed"),
        _claim("demand_durability", "contract_cancelled"),
    ]
    ev = derive_axes(claims)
    assert ev["demand_durability"]["conflict"] is True
    assert ev["demand_durability"]["confidence"] == "low"
    p = build_profile("TEST", ["ai_infra"], {}, evidence=ev)
    assert "demand_durability" in p["conflicts"]
    assert p["evidence_confidence"] == "low"


def test_approved_utilization_evidence_upgrades_axis():
    ev = derive_axes([_claim("utilization_health", "utilization_rising"),
                      _claim("utilization_health", "capacity_sold_out")])
    p = build_profile("TEST", ["ai_infra"], {}, evidence=ev)
    assert p["utilization_health"] == "rising"
    assert "utilization_health" in p["evidence_axes"]
    assert p["source"] == "evidence"


def test_stale_evidence_ignored():
    ev = derive_axes([_claim("utilization_health", "utilization_rising",
                             source_date=STALE)], now=NOW)
    # stale claim counted for audit but produces no axis verdict
    assert "utilization_health" not in ev or ev[
        "utilization_health"]["stale"] == 1
    p = build_profile("TEST", ["ai_infra"], {}, evidence=ev)
    assert p["utilization_health"] == "unknown"


def test_funding_risk_measured_then_escalate_only():
    scalars = {"fcf_ttm": -1e9, "total_debt": 3e9,
               "cash_and_equivalents": 1e9}
    # measured → high (fcf<=0 AND d/c>2); positive evidence can't
    # downgrade it
    ev_pos = derive_axes(
        [_claim("capital_funding_risk", "prepayment_received")])
    p = build_profile("TEST", ["ai_infra"], scalars, evidence=ev_pos)
    assert p["capital_funding_risk"] == "high"
    # refinancing evidence escalates one notch
    ev_neg = derive_axes(
        [_claim("capital_funding_risk", "refinancing_risk")])
    p2 = build_profile("TEST", ["ai_infra"], scalars, evidence=ev_neg)
    assert p2["capital_funding_risk"] == "critical"


def test_funding_evidence_alone_cannot_fabricate_level():
    # no measured financials → unknown; negative evidence escalates
    # to high (conservative), positive evidence leaves unknown alone
    ev = derive_axes(
        [_claim("capital_funding_risk", "refinancing_risk")])
    p = build_profile("TEST", ["ai_infra"], {}, evidence=ev)
    assert p["capital_funding_risk"] == "high"
    ev2 = derive_axes(
        [_claim("capital_funding_risk", "debt_repaid")])
    p2 = build_profile("TEST", ["ai_infra"], {}, evidence=ev2)
    assert p2["capital_funding_risk"] == "unknown"


def test_demand_model_reclassified_by_filing():
    ev = derive_axes(
        [_claim("demand_model", "segment_disclosure",
                value={"demand_model": "recurring_software"})])
    p = build_profile("TEST", ["ai_infra"], {}, evidence=ev)
    assert p["demand_model"] == "recurring_software"
    # durability follows the redefined model
    assert p["demand_durability"] == "recurring"


def test_low_durability_not_compounder_flag():
    # tactical eligibility is separate — a weak-demand name keeps
    # its high impact multiplier and discretionary durability
    p = build_profile("TEST", ["ai_infra"],
                      {"fcf_ttm": 1e8, "total_debt": 1e8,
                       "cash_and_equivalents": 5e8})
    assert p["demand_durability"] in ("discretionary", "speculative",
                                      "unknown")
    assert p["impact_mult"] >= 1.0  # fragile model, not damped


# ── validation ─────────────────────────────────────────────────────

def test_validate_claim_rejects_bad_input():
    assert validate_claim({"axis": "bogus", "signal": "x",
                           "claim": "c", "source": "s"})
    assert validate_claim({"axis": "utilization_health",
                           "signal": "not_a_signal", "claim": "c",
                           "source": "s"})
    assert validate_claim({"axis": "utilization_health",
                           "signal": "utilization_rising",
                           "claim": "", "source": "s"})
    future = (NOW + timedelta(days=30)).isoformat()
    assert validate_claim({"axis": "utilization_health",
                           "signal": "utilization_rising",
                           "claim": "c", "source": "s",
                           "source_date": future})
    assert validate_claim({"axis": "utilization_health",
                           "signal": "utilization_rising",
                           "claim": "c", "source": "s",
                           "source_date": RECENT,
                           "confidence": "high"}) == []
