"""Competitive risk engine — threat exposure math, stage caps,
direction handling, leg scoring, displacement gate. Pure ctx dicts
and synthetic claim lists; no DB, no network."""
from app.signals import competitive_risk as cr


def _threat(comp="RISC-V", tt="substitution", seg="dc CPU IP",
            stage="design_win", direction="threat",
            lo=0.10, hi=0.25, prob=0.5, claim="test claim",
            source="framework_doc", sid=1):
    return {"id": sid, "competitor": comp, "threat_type": tt,
            "segment": seg, "stage": stage, "direction": direction,
            "share_at_risk_lo": lo, "share_at_risk_hi": hi,
            "probability": prob, "claim": claim, "source": source,
            "source_ref": None, "source_date": None,
            "confidence": "medium", "status": "approved"}


def _ctx(**over):
    c = {"symbol": "ARM",
         "om_now": 0.30, "om_slope": 0.04, "gm_slope": 0.02,
         "fcf_margin": 0.28, "fcf_ttm": 1e9, "rd_rev": 0.15,
         "top1_pct": 0.12, "crpo_share": 0.4, "durability_rank": 3,
         "margin_trend": 2, "design_wins_n": 2,
         "moat_mechs": 3, "bottleneck_mechs": 1,
         "threats_n": 0, "threat_exposure": None,
         "insource_exposure": None, "insource_threats_n": 0,
         "competitor_prod_n": 0, "competitor_qual_n": 0,
         "platform_threat_prod": False, "pricing_threat_prod": False,
         "displacement_confirmed": False}
    c.update(over)
    return c


# ---------------- exposure math -------------------------------------

def test_exposure_stage_weighted():
    t = [_threat(stage="production", lo=0.10, hi=0.20, prob=0.5)]
    # mid .15 x prob .5 x mult .80 = .06
    assert abs(cr._exposure(t) - 0.06) < 1e-9


def test_exposure_announced_discounted():
    t = [_threat(stage="announced", lo=0.10, hi=0.20, prob=0.5)]
    # mid .15 x .5 x .10 = .0075
    assert abs(cr._exposure(t) - 0.0075) < 1e-9


def test_exposure_opportunity_never_counts_as_risk():
    t = [_threat(direction="opportunity", stage="production",
                 lo=0.20, hi=0.30, prob=0.5)]
    assert cr._exposure(t, direction="threat") == 0.0
    assert cr._exposure(t, direction="opportunity") > 0


def test_exposure_missing_share_skips():
    t = [_threat(lo=None, hi=None)]
    assert cr._exposure(t) == 0.0


# ---------------- threat ctx aggregation ----------------------------

def test_threat_ctx_counts_stages():
    t = [_threat(stage="production", sid=1),
         _threat(stage="design_win", sid=2),
         _threat(stage="qualification", sid=3)]
    c = cr._threat_ctx(t)
    assert c["competitor_prod_n"] == 1
    assert c["competitor_qual_n"] == 2
    assert c["threats_n"] == 3


def test_displacement_confirmed_hard_to_reach():
    # production + share_lo .15 + prob .5 -> confirmed
    t = [_threat(stage="production", lo=0.15, prob=0.5)]
    assert cr._threat_ctx(t)["displacement_confirmed"] is True
    # design_win same size -> NOT confirmed (not production)
    t = [_threat(stage="design_win", lo=0.30, prob=0.9)]
    assert cr._threat_ctx(t)["displacement_confirmed"] is False
    # production but small share -> NOT confirmed
    t = [_threat(stage="production", lo=0.05, prob=0.5)]
    assert cr._threat_ctx(t)["displacement_confirmed"] is False


def test_platform_and_pricing_prod_flags():
    t = [_threat(tt="platform", stage="production"),
         _threat(tt="pricing", stage="announced", sid=2)]
    c = cr._threat_ctx(t)
    assert c["platform_threat_prod"] is True
    assert c["pricing_threat_prod"] is False


# ---------------- leg scoring ----------------------------------------

def test_pre_production_cap_at_60():
    """A design_win-stage threat can push a leg to the cap but no
    lower — announcements can't sink a moat."""
    ctx = _ctx(threats_n=1, threat_exposure=0.40)
    s = cr._score(ctx, [_threat(stage="design_win")])
    leg = s["components"]["substitution_resist"]
    assert leg["score"] == 60          # band said 15, capped to 60
    assert "capped" in (leg["note"] or "")


def test_production_threat_can_sink_leg():
    ctx = _ctx(threats_n=1, threat_exposure=0.40)
    s = cr._score(ctx, [_threat(stage="production")])
    assert s["components"]["substitution_resist"]["score"] == 15


def test_unknown_legs_excluded():
    ctx = _ctx(rd_rev=None, moat_mechs=None, bottleneck_mechs=None,
               crpo_share=None, durability_rank=None)
    s = cr._score(ctx, [])
    assert s["components"]["technology_moat"]["unknown"] is True
    assert s["crs"] is not None        # renormalizes over the rest


def test_no_threats_is_unverified_not_safe():
    ctx = _ctx(threats_n=0, threat_exposure=None,
               durability_rank=None)
    s = cr._score(ctx, [])
    leg = s["components"]["substitution_resist"]
    assert leg["score"] == 60
    assert "unverified" in (leg["note"] or "")


def test_displacement_caps_crs():
    ctx = _ctx(threats_n=1, threat_exposure=0.05,
               displacement_confirmed=True)
    s = cr._score(ctx, [_threat(stage="production")])
    assert s["crs"] is not None and s["crs"] <= 35
    assert s["capped"]


# ---------------- end-to-end evaluate (pure parts) -------------------

def test_strong_name_scores_resilient():
    ctx = _ctx(threats_n=1, threat_exposure=0.03,
               insource_exposure=0.0)
    s = cr._score(ctx, [_threat(stage="announced",
                                lo=0.02, hi=0.04)])
    assert s["crs"] is not None and s["crs"] >= 60
    assert s["coverage_pct"] is not None and s["coverage_pct"] > 0.5


def test_top_threats_carries_provenance():
    threats = [_threat(stage="production", lo=0.10, hi=0.25,
                      claim="RISC-V dc CPU wins")]
    top = cr._top_threats(threats)
    assert top[0]["competitor"] == "RISC-V"
    assert top[0]["stage"] == "production"
    assert top[0]["share"] == [0.10, 0.25]
    assert top[0]["claim"] == "RISC-V dc CPU wins"
    assert top[0]["source"] == "framework_doc"


def test_insource_exposure_separate_track():
    t = [_threat(tt="insourcing", stage="production",
                 lo=0.10, hi=0.20, prob=0.5)]
    c = cr._threat_ctx(t)
    assert c["insource_threats_n"] == 1
    assert c["insource_exposure"] is not None \
        and c["insource_exposure"] > 0
    assert c["threat_exposure"] == 0.0   # insourcing not in sub set
