"""Metals Pulse — deterministic layer tests.

No DB or network: every test feeds macro/metric dicts directly.
Covers the spec-critical cases — macro classification split (the
same fact must diverge per metal), fear-entry verdicts, falling-knife
gating, missing-data fail-closed.
"""
from app.metals import macro, scoring


def _bullish_macro():
    return {"real_yield_level": 1.4, "real_yield_chg20": -0.15,
            "dxy_chg20": -1.5, "breakeven_chg20": 0.08,
            "hy_level": 3.2, "hy_chg20": -0.05,
            "indpro_yoy": 1.2, "liquidity_score": 65,
            "liquidity_direction": "improving",
            "copper_ret60": 8.0, "fxi_ret60": 6.0,
            "gs_ratio_pctile": 78.0}


def _deflationary_macro():
    return {"real_yield_level": 1.9, "real_yield_chg20": 0.12,
            "dxy_chg20": 1.5, "breakeven_chg20": -0.10,
            "hy_level": 5.4, "hy_chg20": 0.45,
            "indpro_yoy": -1.5, "liquidity_score": 35,
            "liquidity_direction": "deteriorating",
            "copper_ret60": -9.0, "fxi_ret60": -8.0,
            "gs_ratio_pctile": 92.0}


def _fear_metrics():
    return {"off_52w_high_pct": -0.22, "dist_sma200_pct": -0.12,
            "rsi14": 28.0, "ret5": -0.5, "ret20": -8.0}


def _extended_metrics():
    return {"off_52w_high_pct": -0.02, "dist_sma200_pct": 0.09,
            "rsi14": 68.0, "ret5": 2.0, "ret20": 6.0}


class TestMacroClassification:
    def test_precious_bullish(self):
        r = macro.classify(_bullish_macro())
        assert r["label"] == "precious_bullish"
        assert r["components"]["yields"] == "falling"
        assert r["components"]["dollar"] == "weak"

    def test_industrial_bullish(self):
        m = _bullish_macro()
        m["real_yield_chg20"] = 0.02      # yields flat — not precious
        m["dxy_chg20"] = -0.2
        r = macro.classify(m)
        assert r["label"] == "industrial_bullish"

    def test_deflationary_risk(self):
        r = macro.classify(_deflationary_macro())
        assert r["label"] == "deflationary_risk"
        assert r["components"]["credit"] == "stress"

    def test_stagflationary(self):
        m = _deflationary_macro()
        m["breakeven_chg20"] = 0.10       # inflation firm despite
        m["indpro_yoy"] = -1.0            # weak growth
        r = macro.classify(m)
        assert r["label"] == "stagflationary"

    def test_neutral(self):
        r = macro.classify({k: None for k in _bullish_macro()})
        assert r["label"] == "neutral"

    def test_none_tolerant(self):
        r = macro.classify({})
        assert r["label"] == "neutral"


class TestFundamentalScore:
    def test_gold_benefits_from_falling_yields(self):
        f, miss, _ = scoring.fundamental("gold", _bullish_macro())
        assert f is not None and f >= 65
        assert miss == []

    def test_copper_suffers_in_deflation(self):
        f, _, _ = scoring.fundamental("copper", _deflationary_macro())
        assert f is not None and f <= 40

    def test_gold_holds_better_than_copper_in_stress(self):
        m = _deflationary_macro()
        fg, _, _ = scoring.fundamental("gold", m)
        fc, _, _ = scoring.fundamental("copper", m)
        # the metals-regime point: same macro, divergent reads —
        # credit stress is a haven bid for gold but recession for Cu
        assert fg > fc

    def test_missing_legs_renormalize_and_report(self):
        m = {"real_yield_chg20": -0.15, "dxy_chg20": -1.5}
        f, miss, _ = scoring.fundamental("gold", m)
        assert f is not None                    # 3 legs incl. structural
        assert "liquidity" in miss
        assert "credit_haven" in miss

    def test_fail_closed_below_coverage(self):
        f, miss, _ = scoring.fundamental("gold", {})   # only structural (.10)
        assert f is None                        # <40% weight coverage


class TestFearScore:
    def test_deep_discount_high_fear(self):
        e, _, _ = scoring.fear(_fear_metrics())
        assert e is not None and e >= 60

    def test_extended_low_fear(self):
        e, _, _ = scoring.fear(_extended_metrics())
        assert e is not None and e <= 20

    def test_empty_metrics_none(self):
        e, miss, _ = scoring.fear({})
        assert e is None


class TestVerdict:
    def test_accumulate_fear_entry(self):
        v = scoring.verdict("gold", f=65, e=60, regime="precious_bullish",
                            stabilized=True, knife=False)
        assert v == "accumulate"

    def test_strong_accumulate(self):
        v = scoring.verdict("silver", f=80, e=70,
                            regime="precious_bullish",
                            stabilized=True, knife=False)
        assert v == "strong_accumulate"

    def test_extended_waits_for_pullback(self):
        v = scoring.verdict("gold", f=65, e=15, regime="neutral",
                            stabilized=True, knife=False)
        assert v == "wait_for_pullback"

    def test_falling_knife_capped_at_watch(self):
        # high fear still accelerating down — fear alone is not a buy
        v = scoring.verdict("copper", f=65, e=75, regime="neutral",
                            stabilized=False, knife=True)
        assert v == "watch"

    def test_deflationary_risk_reduces_copper(self):
        v = scoring.verdict("copper", f=58, e=70,
                            regime="deflationary_risk",
                            stabilized=True, knife=False)
        assert v == "reduce"

    def test_deflationary_risk_gold_unaffected_when_strong(self):
        # the split the whole engine exists for: same regime, gold's
        # monetary leg can still carry an accumulate
        v = scoring.verdict("gold", f=75, e=68,
                            regime="deflationary_risk",
                            stabilized=True, knife=False)
        assert v in ("accumulate", "strong_accumulate")

    def test_broken_fundamentals_reduce(self):
        v = scoring.verdict("copper", f=25, e=90, regime="neutral",
                            stabilized=True, knife=False)
        assert v == "reduce"

    def test_no_score(self):
        assert scoring.verdict("gold", None, 50, "neutral",
                               None, False) == "no_score"


class TestStabilization:
    def test_knife_detection(self):
        stab, knife = scoring.stabilization(
            {"rsi14": 30.0, "ret5": -6.0, "ret20": -10.0})
        assert knife and not stab

    def test_stabilized_bounce(self):
        stab, knife = scoring.stabilization(
            {"rsi14": 33.0, "ret5": 1.0, "ret20": -6.0})
        assert stab and not knife

    def test_missing_inputs(self):
        stab, knife = scoring.stabilization({})
        assert stab is None and not knife


class TestReasonsAndLegs:
    def test_fundamental_legs_carry_evidence(self):
        f, miss, legs = scoring.fundamental("gold", _bullish_macro())
        names = {l["name"] for l in legs}
        assert "real_yields" in names and "dollar" in names
        ry = next(l for l in legs if l["name"] == "real_yields")
        assert "-0.15" in ry["value"]              # actual input shown
        assert ry["score"] > 70                    # falling = bullish

    def test_fear_legs_carry_evidence(self):
        e, _, legs = scoring.fear(_fear_metrics())
        dd = next(l for l in legs if l["name"] == "drawdown")
        assert "-22.0%" in dd["value"]

    def test_verdict_reason_shows_values(self):
        r = scoring.verdict_reason(
            "gold", "accumulate", 68, 62, "precious_bullish",
            True, False)
        assert "68" in r and "62" in r
        assert "discounted" in r

    def test_knife_reason(self):
        r = scoring.verdict_reason(
            "copper", "watch", 65, 75, "neutral", False, True)
        assert "knife" in r.lower()


class TestTransitions:
    def _snap(self, regime, metals):
        return {"as_of": "2026-10-30", "macro": {"label": regime},
                "metals": {k: {"verdict": v, "fundamental": f,
                               "fear": e}
                           for k, (v, f, e) in metals.items()}}

    def test_newly_actionable_on_upgrade(self):
        prev = self._snap("neutral",
                          {"gold": ("watch", 58, 62)})
        now = self._snap("precious_bullish",
                         {"gold": ("accumulate", 68, 65)})
        t = scoring.transitions(prev, now)
        assert t["macro_flipped"]
        assert t["metals"]["gold"]["newly_actionable"]

    def test_fundamental_cross_while_discounted(self):
        # verdict unchanged at watch→watch is skipped, but a cross
        # from <60 to ≥60 fundamentals with fear still high flags —
        # the window opened even if the label hasn't caught up
        prev = self._snap("neutral",
                          {"silver": ("watch_starter", 57, 66)})
        now = self._snap("precious_bullish",
                         {"silver": ("watch_starter", 63, 66)})
        t = scoring.transitions(prev, now)
        assert t["metals"]["silver"]["newly_actionable"]

    def test_quiet_day_no_flags(self):
        prev = self._snap("neutral", {"gold": ("accumulate", 70, 62)})
        now = self._snap("neutral", {"gold": ("accumulate", 71, 62)})
        t = scoring.transitions(prev, now)
        assert not t["macro_flipped"]
        assert t["metals"] == {}

    def test_first_run(self):
        t = scoring.transitions(None, self._snap("neutral", {}))
        assert t["first_run"]


class TestStabilizationV2:
    def test_rsi_lifting_counts_as_stabilized(self):
        stab, knife = scoring.stabilization(
            {"rsi14": 36.0, "rsi14_5ago": 30.0,
             "ret5": -3.0, "ret20": -8.0, "above_ema20": False})
        assert stab and not knife            # turn signal, not pause

    def test_ema_reclaim_counts_as_stabilized(self):
        stab, knife = scoring.stabilization(
            {"rsi14": 37.0, "rsi14_5ago": 36.5,
             "ret5": -2.5, "ret20": -6.0, "above_ema20": True})
        assert stab and not knife
