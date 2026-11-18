"""recovery_verdict — state machine, gates, conflicts, missing inputs.

The composer is pure: inject snapshots, assert state/decision.
Contract: promotion needs stage-by-stage progress; demotion is free;
absent data is NOT a negative signal; conflicts surface, never average.
"""
from datetime import datetime

from app.signals.recovery_snapshots import Snap
from app.signals.recovery_verdict import build_recovery_verdict

NOW = datetime(2026, 11, 17, 14, 0)


def _snap(data=None, avail=True, ref="t"):
    return Snap(available=avail, as_of="2026-11-17",
                source_ref=ref, data=data or {})


def _stress_regime(**kw):
    d = {"regime": "risk_off", "score": 36, "fragility": 60,
         "dip_character": "broad_deleveraging",
         "stress_direction": "worsening",
         "permissions": {"normal_long": False}}
    d.update(kw)
    return _snap(d)


def _good_fund():
    return _snap({"thesis_status": "on_track", "fundamental_state": "ok"})


def _broken_fund():
    return _snap({"thesis_status": "broken"})


class TestStateMachine:
    def test_no_snapshots_is_normal_with_missing(self):
        v = build_recovery_verdict(
            "X", NOW, Snap(), Snap(), Snap(), Snap(), Snap(), Snap())
        assert v["state"] == "NORMAL"
        assert set(v["missing_inputs"]) == {
            "regime", "selloff", "tape", "intraday", "permission",
            "fundamental"}
        assert v["decision"]["confidence"] == "low"

    def test_liquidation_gives_exhaustion_and_caps_watch(self):
        v = build_recovery_verdict(
            "COHR", NOW, _stress_regime(), Snap(), Snap(), Snap(),
            Snap(), _good_fund())
        assert v["state"] == "EXHAUSTION"
        assert v["decision"]["action"] == "WATCH"
        assert v["decision"]["gates"]["market_liquidation_inactive"] is False

    def test_broken_thesis_is_impairment(self):
        v = build_recovery_verdict(
            "UPST", NOW, _snap(), Snap(), Snap(), Snap(), Snap(),
            _broken_fund())
        assert v["state"] == "STRUCTURAL_IMPAIRMENT"
        assert v["decision"]["action"] == "AVOID"

    def test_no_multi_stage_jump(self):
        # sustained buying + lows + RS + all good: still only one step
        intra = _snap({"signal": "sustained_buying",
                       "detail": {"higher_lows": True,
                                  "vwap_reclaim": True,
                                  "rel_strength": True}})
        v = build_recovery_verdict(
            "COHR", NOW, _snap(), Snap(), Snap(), intra, Snap(),
            _good_fund(), prev_state="NORMAL",
            prev_state_at="2026-11-16")
        assert v["state"] in ("EXHAUSTION", "STABILIZATION")
        assert v["state"] != "RECOVERY"   # cannot skip stages

    def test_stabilization_promotes_on_confirmation(self):
        intra = _snap({"signal": "sustained_buying",
                       "detail": {"higher_lows": True,
                                  "vwap_reclaim": True,
                                  "rel_strength": True}})
        v = build_recovery_verdict(
            "COHR", NOW, _snap(), Snap(), Snap(), intra, Snap(),
            _good_fund(), prev_state="STABILIZATION",
            prev_state_at="2026-11-16")
        assert v["state"] in ("RETEST", "RECOVERY")

    def test_decay_after_idle_stabilization(self):
        v = build_recovery_verdict(
            "X", NOW, _snap(), Snap(), Snap(), Snap(), Snap(),
            _good_fund(), prev_state="STABILIZATION",
            prev_state_at="2026-11-05")     # 12 idle days
        assert v["state"] == "NORMAL"

    def test_demotion_is_immediate(self):
        v = build_recovery_verdict(
            "COHR", NOW, _stress_regime(), Snap(), Snap(), Snap(),
            Snap(), _good_fund(), prev_state="RECOVERY",
            prev_state_at="2026-11-16")
        assert v["state"] in ("EXHAUSTION",)  # drops straight down


class TestConflicts:
    def test_exhaustion_vs_demand_conflict(self):
        intra = _snap({"signal": "sustained_buying",
                       "detail": {"vwap_reclaim": True}})
        sel = _snap({"event_type": "capitulation"})
        v = build_recovery_verdict(
            "COHR", NOW, _stress_regime(), sel, Snap(), intra, Snap(),
            _good_fund())
        assert v["decision"]["conflicts"], "disagreement must surface"
        assert v["decision"]["confidence"] in ("provisional", "low")

    def test_missing_fundamentals_caps_decision(self):
        intra = _snap({"signal": "sustained_buying",
                       "detail": {"higher_lows": True,
                                  "vwap_reclaim": True,
                                  "rel_strength": True}})
        v = build_recovery_verdict(
            "COHR", NOW, _snap(), Snap(), Snap(), intra, Snap(),
            Snap(), prev_state="STABILIZATION",
            prev_state_at="2026-11-15")
        assert v["decision"]["action"] == "WATCH"
        assert "fundamental" in v["missing_inputs"]
