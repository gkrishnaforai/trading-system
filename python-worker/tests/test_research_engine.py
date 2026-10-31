"""Research engine — deterministic layer tests.

No DB required: every test feeds ctx/rows directly. Covers the
spec's critical cases — reproducibility, missing-data fail-closed,
hard-gate precedence, quarter math, sector config.
"""
import pytest

from app.research import (design_wins, fdce, observations, policy,
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


class TestUnknownEvidence:
    """The ARM review's core fix: missing evidence is UNKNOWN —
    excluded and coverage-dropping, never a silent zero."""

    def test_missing_input_unknown_not_zero(self):
        # exposed_rev_growth missing → product_growth unmeasurable →
        # unknown (excluded), not the old 0/25
        ctx = {"model": "connectivity_silicon",
               "exposed_rev_growth": None, "nextgen_stage_rank": 4,
               "products_mapped": 3,
               "dw_reviewed": True, "dw_total": 4, "dw_production": 2,
               "dw_pipeline": 2, "dw_customers": 3,
               "dw_conversion": 0.5, "top1_pct": 0.30,
               "margin_trend": "improving", "om_now": 0.35,
               "rev_products": 2, "pipeline_products": 1}
        r = scores.evaluate("ARM", "ai_infra_architecture", ctx)
        pg = r["components"]["product_growth"]
        assert pg["unknown"] and pg["score"] is None
        # total renormalizes over answered weight — a 0 isn't
        # averaged in, so the score isn't dragged down by thin data
        assert r["score"] > 60
        assert r["coverage"] < 1.0
        assert "product_growth" in r["unknown_components"]

    def test_no_product_map_marks_components_unknown(self):
        ctx = _isrg_ctx()
        ctx.update({"products_mapped": 0, "moat_mechs": 0,
                    "rev_products": 0, "pipeline_products": 0,
                    "rollout_products": 0})
        r = scores.evaluate("ARM", "ai_tailwind", ctx)
        for comp in ("product_differentiation", "moat",
                     "adoption_monetization"):
            assert r["components"][comp].get("unknown"), comp
        # runway still answers — emerging_growth is a real evidence
        # channel (forward-growth flag), not missing data
        assert r["components"]["runway_expansion"]["score"] == 50
        assert r["coverage"] < 0.7

    def test_products_mapped_no_moat_is_a_real_score(self):
        # mapped products with zero moat mechanisms → confirmed-low,
        # not unknown — absence IS the evidence here
        ctx = _isrg_ctx()
        ctx.update({"moat_mechs": 0})
        r = scores.evaluate("X", "ai_tailwind", ctx)
        assert r["components"]["moat"]["score"] == 15
        assert not r["components"]["moat"].get("unknown")

    def test_dw_unreviewed_unknown_vs_examined_zero(self):
        ctx = {"model": "ip_licensing",
               "exposed_rev_growth": 0.2, "nextgen_stage_rank": 4,
               "products_mapped": 3, "top1_pct": 0.20,
               "margin_trend": "improving", "om_now": 0.40,
               "rev_products": 2, "pipeline_products": 1}
        # never examined → unknown
        r1 = scores.evaluate("ARM", "ai_infra_architecture",
                             dict(ctx, dw_reviewed=False, dw_total=0))
        assert r1["components"]["design_wins"].get("unknown")
        # examined, none found → confirmed-low 10
        r2 = scores.evaluate("ARM", "ai_infra_architecture",
                             dict(ctx, dw_reviewed=True, dw_total=0,
                                  dw_production=0, dw_pipeline=0,
                                  dw_customers=0, dw_conversion=None))
        dw = r2["components"]["design_wins"]
        assert dw["score"] == 10 and not dw.get("unknown")


class TestPolicy:
    def test_hard_gate_is_exit_risk(self):
        # risk gates are not thesis failure — exit_risk, not exit_thesis
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 95, "bstrength": 90,
                    "hard_gate": True, "evidence_coverage": 1.0})
        assert policy.evaluate(ctx)["action"] == "exit_risk"

    def test_broken_thesis_is_exit_thesis(self):
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 95, "bstrength": 90,
                    "thesis_status": "broken",
                    "evidence_coverage": 1.0})
        assert policy.evaluate(ctx)["action"] == "exit_thesis"

    def test_strong_profile_accumulates(self):
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 80, "bstrength": 75,
                    "evidence_coverage": 1.0})
        assert policy.evaluate(ctx)["action"] == "accumulate_candidate"

    def test_no_product_map_is_incomplete_not_exit(self):
        # missing coverage can never trigger an exit — the ARM case
        ctx = {k: None for k in _isrg_ctx()}
        ctx.update({"thesis_status": None, "hard_gate": False,
                    "products_mapped": 0,
                    "evidence_coverage": 0.3})
        r = policy.evaluate(ctx)
        assert r["action"] == "research_incomplete"
        assert "exit" not in r["action"]

    def test_thin_coverage_blocks_conviction(self):
        # high scores on 40% coverage → research_incomplete, not accumulate
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 80, "bstrength": 75,
                    "products_mapped": 2,
                    "evidence_coverage": 0.4})
        assert policy.evaluate(ctx)["action"] == "research_incomplete"

    def test_hold_review_plus_incomplete_flag(self):
        # ARM pattern: thesis intact, thin coverage →
        # HOLD_REVIEW + research_incomplete flag
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 40, "bstrength": 62,
                    "products_mapped": 3,
                    "evidence_coverage": 0.6})
        r = policy.evaluate(ctx)
        assert r["action"] == "hold_review"
        assert "research_incomplete" in r["flags"]

    def test_dilution_burner_is_exit_risk(self):
        ctx = _isrg_ctx()
        ctx.update({"ai_tailwind": 70, "bstrength": 60,
                    "dilution_pct": 0.20, "fcf_ttm": -1e8,
                    "evidence_coverage": 1.0})
        assert policy.evaluate(ctx)["action"] == "exit_risk"


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

    def test_arm_is_ip_licensing_not_merchant_silicon(self):
        # ARM's economics are royalty+license — its segments are
        # "Royalties"/"License", its next-gen layer is cpu IP
        assert sectors.classify_model("ARM", "ai_infra") \
            == "ip_licensing"
        m = sectors.model_cfg("ip_licensing", "ai_infra")
        assert any("royalt" in t or "licens" in t
                   for t in m["exposure_terms"])
        assert "cpu" in m["nextgen_layers"]

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


def _p(name, layer, stage, si=None, moat=None, rev=None):
    """FDCE product fixture — weight = revenue share if disclosed,
    else strategic importance; never inferred."""
    return {"name": name, "layer": layer, "stage": stage,
            "strategic_importance": si, "revenue_share_pct": rev,
            "moat": moat or [], "synthetic": True}


class TestFdce:
    def test_registry_loads(self):
        cfg = fdce.load()
        assert len(cfg["domains"]) == 12
        assert fdce.in_universe("CRDO") and fdce.in_universe("PLTR")
        assert not fdce.in_universe("JNJ")
        assert cfg["transitions"] and cfg["universe"]

    def test_weighted_exposure_not_membership(self):
        # one minor product vs a core business — different exposure
        minor = fdce.domain_exposure(
            [_p("side gig", "laser", "pipeline", si=10)])
        core = fdce.domain_exposure(
            [_p("transceivers", "transceiver", "revenue", si=90),
             _p("CPO engines", "cpo", "production", si=70)])
        assert minor["connectivity"]["weight"] < \
            core["connectivity"]["weight"]
        assert "connectivity" in core

    def test_ecs_roadmap_cant_masquerade(self):
        # 1 E5 product + 3 E1 roadmap products (equal weight) →
        # honest mid ECS, high roadmap share — not "mature"
        prods = [_p("core", "gpu", "revenue", si=25),
                 _p("fut1", "cpo", "aspiration", si=25),
                 _p("fut2", "hbm", "aspiration", si=25),
                 _p("fut3", "lidar_radar", "aspiration", si=25)]
        e = fdce.ecs(prods)
        assert e["highest_evidence_stage"].startswith("E5")
        assert e["roadmap_exposure_pct"] == pytest.approx(0.75)
        # mean E = (5+1+1+1)/4 = 2.0; synthetic rows carry conf=0.5
        # → ECS = 2.0 × 0.5 × 20 = 20 — a roadmap majority cannot
        # borrow the E5 product's maturity
        assert e["ecs"] == pytest.approx(20, abs=1)
        # curated/verified evidence (conf=1) doubles it — same book
        for p in prods:
            p["confidence"] = 0.9
        assert fdce.ecs(prods)["ecs"] == pytest.approx(36, abs=1)

    def test_transition_product_level_both_signs(self):
        # NVDA-shaped: gpu at_risk + nic/platform gains → mixed
        prods = [_p("GPU systems", "gpu", "revenue", si=80),
                 _p("Spectrum-X fabric", "switch_silicon", "revenue",
                    si=40)]
        t = fdce.transition_exposure(prods)
        classes = {h["classification"] for h in t["items"]}
        assert "at_risk" in classes
        assert ("direct_beneficiary" in classes
                or "indirect_beneficiary" in classes)
        assert t["net"] == "mixed"

    def test_fdcs_deterministic_and_caps(self):
        ctx = {"model": "connectivity_silicon", "demand_score": 85,
               "bottleneck_mechs": 2, "nextgen_stage_rank": 4,
               "moat_mechs": 3, "dw_total": 3, "dw_production": 2,
               "dw_pipeline": 1, "dw_conversion": 0.67,
               "rev_products": 2, "top1_pct": 0.30,
               "margin_trend": "improving", "om_now": 0.3,
               "fcf_ttm": 1e9, "dilution_pct": 0.01,
               "domain_count": 2}
        r1 = scores.evaluate("CRDO", "future_demand_capture", ctx)
        r2 = scores.evaluate("CRDO", "future_demand_capture", ctx)
        assert r1["score"] == r2["score"] and r1["score"] >= 75
        # spec safeguards: no production → conversion capped at 35
        r3 = scores.evaluate("X", "future_demand_capture",
                             dict(ctx, dw_production=0,
                                  rev_products=0))
        assert r3["components"]["commercial_conversion"]["score"] \
            <= 35
        # no moat → competitive advantage capped at 40
        r4 = scores.evaluate("X", "future_demand_capture",
                             dict(ctx, moat_mechs=0,
                                  bottleneck_mechs=0))
        assert r4["components"]["competitive_advantage"]["score"] \
            <= 40

    def test_adjusted_fdcs_clipped(self):
        assert fdce.adjusted_fdcs(90, -30) == 60
        assert fdce.adjusted_fdcs(95, 20) == 100
        assert fdce.adjusted_fdcs(None, 5) is None

    def test_disruption_flags(self):
        prods = [_p("workflow agent", "orchestration", "revenue",
                    si=60)]
        d = fdce.disruption(prods, set(), 0.55, {"items": []})
        assert d["open_source_commoditization_risk"] == "elevated"
        assert d["customer_concentration_risk"] == "high"
        assert d["replication_difficulty"] == "low"


class TestGenericSector:
    def test_loads_and_self_feeds(self):
        cfg = sectors.load("generic")
        assert cfg["universe"]["tracked"]
        assert cfg["news_scan"]["enabled"]
        assert cfg["scores"] == ["ai_tailwind", "business_strength",
                                 "quality"]

    def test_unrouted_symbol_falls_to_generic(self):
        # not in any curated universe → the book pass, never a
        # forced sector fit
        assert sectors.sector_for_symbol(
            "ZZZZ", row={"sector": "Conglomerates"}) == "generic"
        # curated membership still wins
        assert sectors.sector_for_symbol("CRDO") == "ai_infra"

    def test_generic_universe_is_book_minus_curated(self, monkeypatch):
        import app.research.sectors as S
        from app.database import db

        def fake_exec(sql, params=None):
            if "book_symbols" in sql:          # the tracked tier
                return [{"symbol": s} for s in
                        ("CRDO", "PLTR", "ZZZZ")]
            return []                          # sector_match queries

        monkeypatch.setattr(db, "execute_query", fake_exec)
        u = S.universe("generic")
        assert "ZZZZ" in u
        assert "CRDO" not in u                 # claimed by ai_infra
        assert "PLTR" in u                     # fdce-only → generic run


class TestNewsScan:
    def test_dedupe_and_noise_filter(self, monkeypatch):
        from app.research import news_scan
        from app.database import db
        from app.signals import doc_extract
        monkeypatch.setattr(
            db, "execute_query", lambda *a, **k:
            [{"url": "https://x/seen"}])
        # fetch fail-open — a provider that raises returns zeros,
        # never kills the run
        import app.providers.financial_modeling_prep as fmp
        class _Boom:
            def search_stock_news(self, s):
                raise RuntimeError("no feed")
        monkeypatch.setattr(fmp, "enhanced_fmp_client", _Boom())
        assert news_scan.scan("X")["fetched"] == 0

    def test_filters(self, monkeypatch):
        import app.research.news_scan as ns
        from app.database import db
        from app.signals import doc_extract
        from datetime import date, timedelta
        recent = (date.today() - timedelta(days=2)).isoformat()
        items = [
            {"title": "ARM unveils new AGI CPU for datacenter",
             "url": "https://x/1", "publishedDate": recent,
             "text": "body " * 100},
            {"title": "Why ARM stock is moving today",
             "url": "https://x/2", "publishedDate": recent},
            {"title": "ARM Q1 recap", "url": "https://x/seen",
             "publishedDate": recent, "text": "body " * 100},
            {"title": "ARM old story", "url": "https://x/3",
             "publishedDate": "2020-01-01", "text": "b " * 200},
        ]
        monkeypatch.setattr(db, "execute_query",
                            lambda *a, **k: [{"url": "https://x/seen"}])

        class FakeClient:
            def search_stock_news(self, s):
                return items

        import app.providers.financial_modeling_prep as fmp
        monkeypatch.setattr(fmp, "enhanced_fmp_client", FakeClient())
        calls = []

        def fake_analyze(sym, text="", url="", title=""):
            calls.append(url)
            return {"claims": [{"type": "channel"}]}

        monkeypatch.setattr(doc_extract, "analyze", fake_analyze)
        st = ns.scan("ARM", {"max_articles": 4, "lookback_days": 10})
        assert st["skipped_noise"] == 1
        assert st["skipped_seen"] == 1
        assert st["skipped_stale"] == 1
        assert calls == ["https://x/1"]
        assert st["analyzed"] == 1
