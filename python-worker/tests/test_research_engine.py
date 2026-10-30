"""Research engine — deterministic layer tests.

No DB required: every test feeds ctx/rows directly. Covers the
spec's critical cases — reproducibility, missing-data fail-closed,
hard-gate precedence, quarter math, sector config.
"""
import pytest

from app.research import (design_wins, observations, policy,
                          quarter, scores, sectors)


def _q(rev, om, shares, fcf=6e8, cash=8e9, debt=6e9):
    return {"period_end": "2026-01-01", "filing_date": None,
            "revenue": {"value": rev},
            "gross_margin": {"value": 0.68},
            "op_margin": {"value": om},
            "net_income": {"value": 5e8},
            "eps_diluted": {"value": 1.5},
            "shares_diluted": {"value": shares},
            "cash": {"value": cash}, "total_debt": {"value": debt},
            "free_cf": {"value": fcf}}


def _isrg_ctx():
    return {"model": "devices_robotics", "ai_linkage": "ai_adopter",
            "opportunity_tagged": True, "moat_mechs": 3,
            "products_mapped": 4, "rev_products": 2,
            "rollout_products": 1, "pipeline_products": 2,
            "driver_raises": 1, "driver_cuts": 0,
            "rev_growth": 0.17, "rev_accel": 0.02,
            "est_revision_pct": 0.03, "gq_score": 72,
            "om_now": 0.28, "fcf_margin": 0.24, "fcf_ttm": 2e9,
            "nde": 0.4, "dilution_pct": 0.01,
            "runway_quarters": None, "emerging_growth": True,
            "thesis_status": "on_track", "hard_gate": False}


class TestQuarterMath:
    def test_growth_and_dilution(self):
        qs = [_q(2.1e9, 0.29, 3.60e8), _q(2.0e9, 0.28, 3.59e8),
              _q(1.9e9, 0.27, 3.58e8), _q(1.85e9, 0.26, 3.57e8),
              _q(1.8e9, 0.25, 3.55e8), _q(1.7e9, 0.24, 3.53e8)]
        t = quarter.trends(qs)
        assert abs(t["rev_yoy"] - 0.1667) < 0.001
        assert abs(t["rev_qoq"] - 0.05) < 0.001
        assert t["margin_trend"] == "improving"
        assert abs(t["dilution_yoy"] - 0.0141) < 0.001
        assert t["runway_quarters"] is None  # cash > debt → None

    def test_runway_for_burner(self):
        qs = [_q(1e6, -2.5, 1e8, fcf=-5e7, cash=1e8, debt=1e6)]
        assert quarter.trends(qs)["runway_quarters"] == 2.0
        # one quarter can't be a trend — key stays absent
        assert "margin_trend" not in quarter.trends(qs)

    def test_missing_values_stay_none(self):
        q = {k: {"value": None} for k in
             ("revenue", "gross_margin", "op_margin", "net_income",
              "eps_diluted", "shares_diluted", "cash",
              "total_debt", "free_cf")}
        q["period_end"], q["filing_date"] = "2026-01-01", None
        t = quarter.trends([q])
        assert t.get("rev_yoy") is None
        assert t.get("runway_quarters") is None


class TestScoring:
    def test_reproducible(self):
        ctx = _isrg_ctx()
        a = scores.evaluate("ISRG", "ai_tailwind", ctx)
        b = scores.evaluate("ISRG", "ai_tailwind", dict(ctx))
        assert a["score"] == b["score"]
        assert a["rules_version"].startswith("ai_tailwind@")

    def test_score_bounds_and_weights_sum_100(self):
        for kind in ("ai_tailwind", "business_strength", "quality"):
            spec = scores._spec(kind)
            total = sum(c["weight"]
                        for c in spec["components"].values())
            assert total == pytest.approx(100), kind

    def test_missing_dims_log_not_invent(self):
        ctx = {k: None for k in _isrg_ctx()}
        ctx["products_mapped"] = ctx["rev_products"] = 0
        ctx["moat_mechs"] = 0
        r = scores.evaluate("X", "ai_tailwind", ctx)
        assert r["coverage"] < 0.5
        assert r["missing"]           # absent fields surfaced

    def test_no_linkage_cant_score_high(self):
        ctx = _isrg_ctx()
        ctx["ai_linkage"] = None
        r = scores.evaluate("X", "ai_tailwind", ctx)
        assert r["score"] <= 40
        assert r["capped"]           # cap reason journaled

    def test_model_override_changes_score(self):
        ctx = _isrg_ctx()
        ctx.update({"om_now": -1.0, "fcf_margin": -0.5,
                    "fcf_ttm": -1e8, "rev_growth": 0.8})
        base = scores.evaluate("X", "business_strength", ctx)
        over = scores.evaluate("X", "business_strength", ctx,
                               {"margin_trajectory": 0,
                                "cash_resilience": 30,
                                "capital_discipline": 10})
        assert over["score"] != base["score"]


class TestPolicy:
    def test_hard_gate_outranks_score(self):
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 95, "bstrength": 90,
                    "hard_gate": True})
        assert policy.evaluate(ctx)["action"] == "exit_review"

    def test_broken_thesis_is_exit(self):
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 95, "bstrength": 90,
                    "thesis_status": "broken"})
        assert policy.evaluate(ctx)["action"] == "exit_review"

    def test_strong_profile_accumulates(self):
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 80, "bstrength": 75})
        assert policy.evaluate(ctx)["action"] == "accumulate_candidate"

    def test_no_evidence_researches_not_acts(self):
        ctx = {k: None for k in _isrg_ctx()}
        ctx.update({"thesis_status": None, "hard_gate": False,
                    "products_mapped": 0})
        assert policy.evaluate(ctx)["action"] == "research"

    def test_dilution_burner_exits(self):
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 70, "bstrength": 60,
                    "dilution_pct": 0.20, "fcf_ttm": -1e8})
        assert policy.evaluate(ctx)["action"] == "exit_review"


class TestSectorConfig:
    def test_healthcare_loads_complete(self):
        cfg = sectors.load("healthcare")
        for k in ("opportunities", "business_models",
                  "model_weight_overrides", "risk_gates",
                  "moat_mechanisms", "catalyst_types"):
            assert k in cfg, k

    def test_model_kpis_exist(self):
        m = sectors.model_cfg("drug_discovery")
        assert m["kpis"] and not m["profitability_expected"]

    def test_classify_from_row(self):
        row = {"industry": "Medical Devices"}
        assert sectors.classify_model("ISRG", row=row) == "devices_robotics"
        row = {"industry": "Life Sciences Tools"}
        assert sectors.classify_model("X", row=row) == "research_tools"
        # traditional pharma isn't in the AI-tailwind taxonomy —
        # unclassified is the honest bucket, not a forced fit
        row = {"industry": "Drug Manufacturers"}
        assert sectors.classify_model("Y", row=row) == "unclassified"


class TestAiInfraSector:
    def test_loads_complete(self):
        cfg = sectors.load("ai_infra")
        for k in ("universe", "symbol_map", "layers",
                  "business_models", "moat_mechanisms",
                  "risk_gates", "catalyst_types", "scores"):
            assert k in cfg, k
        assert "ai_infra_architecture" in cfg["scores"]

    def test_symbol_map_beats_industry_text(self):
        # CRDO is connectivity silicon by curated map — industry
        # text never decides the module
        row = {"industry": "Semiconductors"}
        assert sectors.classify_model(
            "CRDO", "ai_infra", row=row) == "connectivity_silicon"
        assert sectors.classify_model(
            "GEV", "ai_infra", row={"industry": "Utilities"}) \
            == "power_gen"

    def test_universe_is_explicit(self):
        u = sectors.universe("ai_infra")
        for s in ("CRDO", "LITE", "COHR", "ALAB", "NVDA", "GEV"):
            assert s in u

    def test_sector_routing(self):
        assert sectors.sector_for_symbol("CRDO") == "ai_infra"
        assert sectors.sector_for_symbol("NVDA") == "ai_infra"

    def test_arch_spec_weights_sum_100(self):
        spec = scores._spec("ai_infra_architecture")
        total = sum(c.get("weight", 0) for c in
                    spec["components"].values())
        assert total == 100

    def test_arch_score_ladder_and_caps(self):
        # production-converted wins + growing exposed segment → high
        ctx = {"model": "connectivity_silicon",
               "exposed_rev_growth": 0.6, "nextgen_stage_rank": 4,
               "dw_total": 4, "dw_production": 2,
               "dw_pipeline": 2, "dw_customers": 3,
               "dw_conversion": 0.5, "top1_pct": 0.30,
               "margin_trend": "improving", "om_now": 0.35,
               "rev_products": 2, "pipeline_products": 1}
        r = scores.evaluate("CRDO", "ai_infra_architecture", ctx)
        assert 75 <= r["score"] <= 95
        # spec discipline: no production wins → cap, regardless of
        # everything else scoring well
        ctx2 = dict(ctx, dw_production=0, dw_total=2,
                    dw_conversion=None, top1_pct=None)
        r2 = scores.evaluate("CRDO", "ai_infra_architecture", ctx2)
        assert r2["score"] <= 60 and r2["capped"]
        # single-customer dependence caps independently
        ctx3 = dict(ctx, top1_pct=0.65)
        r3 = scores.evaluate("CRDO", "ai_infra_architecture", ctx3)
        assert r3["score"] <= 55 and r3["capped"]


class TestDesignWins:
    def test_conversion_math(self):
        rows = [{"customer": "AWS", "product": "AEC",
                 "stage": "production",
                 "revenue_confirmed": True},
                {"customer": "GCP", "product": "optical DSP",
                 "stage": "scaling"},
                {"customer": "Azure", "product": "retimer",
                 "stage": "qualification"}]
        s = design_wins.stats(rows)
        assert s["dw_total"] == 3 and s["dw_production"] == 2
        assert s["dw_pipeline"] == 1 and s["dw_customers"] == 3
        assert s["dw_conversion"] == pytest.approx(2 / 3, abs=0.01)

    def test_revenue_confirmed_counts_as_production(self):
        rows = [{"customer": "Meta", "product": "AEC",
                 "stage": "announced", "revenue_confirmed": True}]
        assert design_wins.stats(rows)["dw_production"] == 1

    def test_empty_is_none_not_zero(self):
        s = design_wins.stats([])
        assert s["dw_total"] == 0 and s["dw_conversion"] is None


class TestExposure:
    def test_no_terms_no_score(self):
        out = observations.exposure("X", [])
        assert out["exposed_rev_growth"] is None
