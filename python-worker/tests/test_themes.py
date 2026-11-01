"""Theme Intelligence — deterministic layer tests.

No DB: every test feeds member/macro dicts directly. Covers scenario
probability math, expected/downside/robustness, the 6-factor score's
missing-leg handling, and index weight caps — the spec's two-version
requirement.
"""
from app.themes import index_builder, opportunity, scenarios
from app.themes.narratives import SCENARIO_PRIORS


def _member(sym="AAA", expo="pure", bs=70, tw=65, rev=8.0, growth=20.0,
            eps=15.0, up=25.0, r20=0.05, r60=0.10, a50=70.0):
    return {"symbol": sym, "exposure": expo,
            "business_strength": bs, "ai_tailwind": tw,
            "est_revision_pct": rev, "rev_growth": growth,
            "eps_growth": eps, "fv_upside_pct": up,
            "ret20": r20, "ret60": r60, "above_sma50": a50,
            "expo_w": index_builder.EXPO_W[expo]}


class TestScenarioProbabilities:
    def test_priors_normalize(self):
        p = scenarios.probabilities({})
        assert abs(sum(p.values()) - 100.0) < 0.5

    def test_bull_tape_shifts_to_growth(self):
        p = scenarios.probabilities({"fwd_bull": 55, "fwd_bear": 15})
        assert p["growth_accel_falling_rates"] > \
            SCENARIO_PRIORS["growth_accel_falling_rates"]

    def test_credit_stress_shifts_to_recession(self):
        p = scenarios.probabilities({"hy_chg20": 0.5})
        assert p["recession_stress"] > \
            SCENARIO_PRIORS["recession_stress"]

    def test_floors_keep_all_scenarios(self):
        p = scenarios.probabilities({"fwd_bull": 90, "fwd_bear": 5,
                                     "liquidity_score": 80})
        assert all(v >= 3.0 for v in p.values())


class TestEvaluateTheme:
    def test_expected_is_prob_weighted(self):
        probs = {"growth_accel_falling_rates": 100.0,
                 "growth_sticky_inflation": 0.0,
                 "moderate_stable": 0.0,
                 "slowdown_falling_rates": 0.0,
                 "recession_stress": 0.0}
        e = scenarios.evaluate_theme("ai_software", probs)
        assert e["expected"] == 88.0       # sensitivity under that
        assert e["robustness"] > e["expected"] or e["robustness"] >= 0

    def test_resilient_theme_outranks_in_stress(self):
        probs = {s: 20.0 for s in SCENARIO_PRIORS}
        grid = scenarios.evaluate_theme("grid_electrification", probs)
        hbm = scenarios.evaluate_theme("hbm_memory", probs)
        assert grid["robustness"] > hbm["robustness"]
        assert grid["downside"] > hbm["downside"]

    def test_unknown_theme_uses_default(self):
        e = scenarios.evaluate_theme("llm_discovered_x",
                                     {s: 20.0 for s in SCENARIO_PRIORS})
        assert e["expected"] is not None

    def test_verdict_bands(self):
        assert scenarios.verdict(85) == "strong"
        assert scenarios.verdict(70) == "attractive"
        assert scenarios.verdict(60) == "selective"
        assert scenarios.verdict(50) == "watch"
        assert scenarios.verdict(30) == "avoid"
        assert scenarios.verdict(None) == "no_score"


class TestOpportunityScore:
    def test_full_legs_score_high(self):
        legs = {"members": [_member(), _member("BBB")],
                "stage": "inflecting",
                "spy_ret20": 0.01, "spy_ret60": 0.02}
        r = opportunity.score("grid_electrification", legs,
                              scenario_expected=80)
        assert r["score"] is not None and r["score"] >= 60
        assert r["missing"] == []

    def test_weak_members_score_low(self):
        weak = _member(bs=25, tw=20, rev=-12.0, growth=-5.0,
                       eps=-10.0, up=-40.0, r20=-0.15, a50=10.0)
        legs = {"members": [weak], "stage": "exhausted",
                "spy_ret20": 0.02, "spy_ret60": 0.05}
        r = opportunity.score("hbm_memory", legs,
                              scenario_expected=25)
        assert r["score"] is not None and r["score"] <= 40

    def test_missing_members_fail_closed(self):
        legs = {"members": [], "stage": "emerging",
                "spy_ret20": 0.01, "spy_ret60": 0.02}
        r = opportunity.score("ai_optics", legs,
                              scenario_expected=70)
        assert r["score"] is None            # only regime+demand live
        assert "earnings" in r["missing"]
        assert "valuation" in r["missing"]

    def test_leg_evidence_carries_values(self):
        legs = {"members": [_member()], "stage": "inflecting",
                "spy_ret20": 0.01, "spy_ret60": 0.02}
        r = opportunity.score("ai_software", legs,
                              scenario_expected=75)
        names = {l["name"] for l in r["legs"]}
        assert {"earnings", "valuation", "momentum"} <= names
        ev = next(l for l in r["legs"] if l["name"] == "earnings")
        assert "rev" in ev["value"]


class TestIndexBuilder:
    def test_pure_vs_quality_versions(self):
        # derivative member with decisively better fundamentals —
        # quality can outrank exposure, pure cannot
        mems = [_member("AAA", bs=30, rev=-8.0, growth=2.0, eps=1.0,
                        up=-10.0),
                _member("BBB", expo="derivative", bs=95, rev=25.0,
                        growth=45.0, eps=40.0, up=80.0)]
        idx = index_builder.build("t", mems)
        assert idx["pure"]["n"] == 2
        assert idx["quality"]["n"] == 2
        # pure weights by exposure tier — AAA pure > BBB derivative
        assert idx["pure"]["weights"]["AAA"] > \
            idx["pure"]["weights"]["BBB"]
        # quality weights by constituent score — BBB outranks
        assert idx["quality"]["weights"]["BBB"] > \
            idx["quality"]["weights"]["AAA"]

    def test_name_cap_enforced(self):
        mems = [_member(f"S{i}", bs=90 if i == 0 else 40,
                        up=60.0 if i == 0 else 5.0)
                for i in range(30)]
        idx = index_builder.build("t", mems)
        assert all(w <= index_builder.MAX_NAME + 1e-6
                   for w in idx["quality"]["weights"].values())

    def test_ineligible_needs_evidence(self):
        mems = [{"symbol": "GHOST", "exposure": "pure",
                 "expo_w": 1.0}]              # zero evidence rows
        idx = index_builder.build("t", mems)
        assert idx["ineligible"] == ["GHOST"]
        assert idx["quality"]["n"] == 0

    def test_small_theme_not_padded(self):
        mems = [_member("AAA"), _member("BBB")]
        idx = index_builder.build("t", mems)
        assert idx["quality"]["n"] == 2       # never padded to 40


class TestPoolAndRoles:
    def test_pool_note_carries_tier_and_facts(self):
        n = index_builder.pool_note(
            "speculative", "x", {"business_strength": 45.0,
                                 "fv_upside_pct": 60.0})
        assert "speculative" in n and "bs 45" in n and "+60%" in n

    def test_pool_note_no_evidence_honest(self):
        n = index_builder.pool_note("pure", "x", {})
        assert "no evidence yet" in n

    def test_role_from_weight_and_tier(self):
        assert index_builder.role(0.05, "pure") == "pure-play anchor"
        assert index_builder.role(0.03, "derivative") == \
            "derivative core"
        assert index_builder.role(0.008, "speculative") == \
            "speculative satellite"

    def test_pool_symbols_score_same_as_members(self):
        # pool names are scored by the same constituent_score —
        # the pool is the funnel, not a different standard
        s = index_builder.constituent_score(_member("POOL", bs=85))
        assert s is not None and s > 60


class TestAdviceAndWhy:
    def test_advice_maps_stance_to_target(self):
        assert index_builder.advice("accumulate_candidate", 0.042) == \
            "build toward 4.2%"
        assert index_builder.advice("trim_candidate", 0.05) == \
            "trim — reduce toward core size"
        assert index_builder.advice("research_incomplete", 0.0) == \
            "research — evidence too thin to size"
        assert index_builder.advice(None, 0.03) == "no stance yet"

    def test_pool_note_curated_why_leads(self):
        n = index_builder.pool_note(
            "pure", "x", {"business_strength": 60.0},
            why="T&D construction EPC — contracted backlog")
        assert n.startswith("T&D construction EPC")
        assert "direct theme exposure" in n
        assert "bs 60" in n

    def test_pool_note_without_why_falls_back(self):
        n = index_builder.pool_note("speculative", "x", {})
        assert n.startswith("speculative pure-play")
