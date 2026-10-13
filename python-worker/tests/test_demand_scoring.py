"""Phase 2 scorer regression tests — regime consensus, warning
escalation, durability score, shadow gate, scenario stress."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.fair_value_v2.demand_score import (  # noqa: E402
    ai_capex_regime, cycle_warning_score, demand_gate,
    demand_scenarios, durability_score)

NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(days=20)).isoformat()
OLD = (NOW - timedelta(days=300)).isoformat()


def _c(signal, **kw):
    base = {"symbol": "X", "signal": signal, "status": "approved",
            "source_date": RECENT, "confidence": "high",
            "axis": "capex_sensitivity"}
    base.update(kw)
    return base


# ── ai_capex_regime ────────────────────────────────────────────────

def test_moderating_capex_with_rising_usage_is_normalization():
    """Framework case: capex growth moderates but usage/monetization
    rise → growth_moderating, NOT a warning regime."""
    claims = [
        _c("customer_capex_guidance_down", symbol="MSFT"),
        _c("utilization_rising", symbol="NBIS"),
        _c("ai_revenue_growing", symbol="GOOGL"),
    ]
    r = ai_capex_regime(claims)
    assert r["regime"] == "growth_moderating"
    assert r["groups"]["spending"] == "down"
    assert r["groups"]["utilization"] == "up"


def test_broad_deterioration_gives_stress():
    claims = [
        _c("customer_capex_guidance_down"),
        _c("order_cancellation"),
        _c("utilization_falling"),
        _c("refinancing_risk"),
    ]
    r = ai_capex_regime(claims)
    assert r["regime"] == "stress"
    assert len(r["down_groups"]) >= 3


def test_contracting_needs_spending_and_orders():
    claims = [_c("customer_capex_guidance_down"),
              _c("order_cancellation")]
    r = ai_capex_regime(claims)
    assert r["regime"] == "contracting"


def test_broad_strength_expands():
    claims = [_c("customer_capex_guidance_up"),
              _c("order_growth"),
              _c("utilization_rising"),
              _c("ai_revenue_growing")]
    assert ai_capex_regime(claims)["regime"] == "accelerating"


def test_no_evidence_is_unknown_not_favorable():
    r = ai_capex_regime([])
    assert r["regime"] == "unknown"
    assert all(d == "unknown" for d in r["groups"].values())


def test_single_company_doesnt_set_regime():
    """One company's guidance cannot be the regime signal."""
    r = ai_capex_regime([_c("customer_capex_guidance_down",
                            symbol="MSFT")])
    assert r["regime"] in ("flat", "unknown")  # only spending down
    assert r["regime"] != "stress"


# ── cycle warning ──────────────────────────────────────────────────

def test_warning_needs_two_down_groups_to_escalate():
    one = cycle_warning_score([_c("order_cancellation")])
    assert one["score"] <= 30 and one["down_groups"] == 1
    # one down + one mixed group exceeds the raw cap but is clamped
    # — a lone deteriorating group can't escalate the warning
    heavy = cycle_warning_score([
        _c("customer_capex_guidance_down"),               # spending 25
        _c("ai_revenue_growing"),                          # monetization
        _c("ai_pricing_pressure"),                         # → mixed 7.5
        ])
    assert heavy["score"] == 30.0 and heavy["capped"]
    two = cycle_warning_score([_c("order_cancellation"),
                               _c("utilization_falling")])
    assert two["score"] > one["score"]
    assert not two["capped"]


def test_stale_market_evidence_ignored():
    w = cycle_warning_score([_c("order_cancellation",
                                source_date=OLD)])
    assert w["score"] == 0.0


# ── durability score ───────────────────────────────────────────────

def _nbis_profile():
    return {"demand_model": "capacity_rental",
            "capex_sensitivity": "medium",
            "demand_durability": "contracted",
            "utilization_health": "unknown",
            "capital_funding_risk": "moderate",
            "ai_monetization": "scaling"}


def test_durability_score_weights_and_coverage():
    d = durability_score(_nbis_profile())
    assert d["score"] is not None
    assert 55 <= d["score"] <= 90   # contracted + rental + scaling
    assert d["coverage"] < 1.0      # diversification excluded
    assert d["confidence"] in ("medium", "high")


def test_evidence_shifts_durability_dimension():
    ev = {"demand_durability": {"pos_score": 2.0, "neg_score": 0.0}}
    p = {**_nbis_profile(), "demand_durability": "usage_based"}
    base = durability_score(p)
    boosted = durability_score(p, evidence=ev)
    assert boosted["score"] > base["score"]
    # negative evidence pulls it below base
    ev_neg = {"demand_durability": {"pos_score": 0.0, "neg_score": 2.0}}
    assert durability_score(p, evidence=ev_neg)["score"] < base["score"]


def test_unknown_axes_dont_fabricate_score():
    d = durability_score({"demand_model": "unknown",
                          "demand_durability": "unknown",
                          "capital_funding_risk": "unknown",
                          "ai_monetization": "unknown"})
    assert d["score"] is None
    assert d["confidence"] == "unknown"


# ── shadow gate ────────────────────────────────────────────────────

def test_critical_funding_blocks_adds():
    g = demand_gate({"capital_funding_risk": "critical",
                     "capex_sensitivity": "medium",
                     "demand_durability": "contracted",
                     "utilization_health": "unknown"},
                    {"regime": "expanding"})
    assert g["gate"] == "block_adds"
    assert g["shadow"] is True          # never applied to action
    assert g["long_term_eligible"] is False


def test_high_sensitivity_moderating_regime_raises_burden():
    g = demand_gate({"capital_funding_risk": "low",
                     "capex_sensitivity": "high",
                     "demand_durability": "discretionary",
                     "utilization_health": "stable"},
                    {"regime": "growth_moderating"})
    assert g["gate"] == "higher_burden"


def test_durable_low_funding_is_long_term_eligible():
    g = demand_gate({"capital_funding_risk": "low",
                     "capex_sensitivity": "medium",
                     "demand_durability": "contracted",
                     "utilization_health": "stable",
                     "conflicts": []},
                    {"regime": "expanding"})
    assert g["gate"] == "permit_add"
    assert g["long_term_eligible"] is True


def test_conflict_blocks_long_term_not_tactical():
    g = demand_gate({"capital_funding_risk": "low",
                     "capex_sensitivity": "medium",
                     "demand_durability": "contracted",
                     "utilization_health": "stable",
                     "conflicts": ["demand_durability"]},
                    {"regime": "expanding"})
    assert g["long_term_eligible"] is False
    assert g["gate"] == "permit_add"    # tactical path unaffected


# ── scenario stress ────────────────────────────────────────────────

def test_scenarios_use_measured_forward_growth():
    p = {"demand_model": "capacity_rental",
         "capex_sensitivity": "medium",
         "demand_durability": "contracted",
         "capital_funding_risk": "moderate",
         "utilization_health": "unknown"}
    s = demand_scenarios(p, {"revenue_ttm": 1.36e9,
                             "revenue_forward": 3.34e9})
    assert abs(s["revenue_growth_base"] - 1.4559) < 0.01
    # capacity_rental shock 0.70/0.40
    assert abs(s["revenue_growth_slowdown"] - 1.0191) < 0.01
    assert s["fcf_stress_state"] == "moderate"
    assert s["thesis_break_conditions"]


def test_scenarios_unknown_without_estimates():
    s = demand_scenarios({"demand_model": "mixed",
                          "capital_funding_risk": "low"}, {})
    assert s["revenue_growth_base"] == "unknown"
    assert s["revenue_growth_stress"] == "unknown"


# ── ingest: deterministic capex claims ─────────────────────────────

from app.fair_value_v2.demand_ingest import capex_claim  # noqa: E402


def _cf(date, capex, period="Q4", fy="2026"):
    return {"date": date, "capitalExpenditure": -abs(capex),
            "period": period, "fiscalYear": fy}


def test_capex_claim_growth_up():
    rows = [
        _cf("2025-03-31", 20e9, "Q4", "2025"),
        _cf("2025-06-30", 22e9, "Q4", "2025"),
        _cf("2025-09-30", 24e9, "Q4", "2025"),
        _cf("2025-12-31", 25e9, "Q4", "2025"),
        _cf("2026-06-30", 34e9, "Q4", "2026"),
    ]
    c = capex_claim("MSFT", rows)
    assert c and c["signal"] == "capex_actuals_up"
    assert c["status"] == "approved"       # measured fact, not LLM
    assert c["confidence"] == "high"


def test_capex_claim_decline_and_flat():
    down = capex_claim("MSFT", [_cf("2025-12-31", 30e9),
                              _cf("2026-06-30", 20e9)])
    assert down["signal"] == "capex_actuals_down"
    flat = capex_claim("MSFT", [_cf("2025-12-31", 30e9),
                              _cf("2026-06-30", 31e9)])
    assert flat is None          # ±3% is noise, not a signal


def test_capex_claim_insufficient_data():
    assert capex_claim("X", [_cf("2026-06-30", 1e9)]) is None
    assert capex_claim("X", []) is None
