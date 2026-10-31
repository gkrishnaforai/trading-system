"""thesis_health — persistence ladder, criticality, coverage, recovery.

The contract under test: a single bad print can never mark a thesis
'broken' — structural impairment requires a hard leg failing across
DISTINCT reporting periods with corroboration, or a fatal veto. Pure
functions only; evaluate() stays DB-bound.
"""
from datetime import date, timedelta

from app.signals.thesis_health import (
    _core_coverage, _hyp_status, _periods, _rollup_status, stance_for)


def _check(status, metric="rev_growth", value=0.10, hard=False, **kw):
    c = {"status": status, "metric": metric, "value": value,
         "note": f"{metric} {value}", "hard": hard}
    c.update(kw)
    return c


# ---------- _periods — what counts as a new reporting period ----------

class TestPeriods:
    def test_first_fail_is_streak_one(self):
        c = _check("fail")
        _periods(c, {})
        assert c["fail_streak"] == 1 and c["pass_streak"] == 0

    def test_same_value_is_same_period(self):
        prev = {"status": "fail", "value": 0.10, "fail_streak": 1,
                "streak_at": (date.today() - timedelta(days=90))
                .isoformat()}
        c = _check("fail", value=0.10)
        _periods(c, prev)
        # same print re-evaluated nightly — no escalation
        assert c["fail_streak"] == 1

    def test_changed_value_inside_gap_window_is_not_new_period(self):
        prev = {"status": "fail", "value": 0.10, "fail_streak": 1,
                "streak_at": (date.today() - timedelta(days=5))
                .isoformat()}
        c = _check("fail", value=0.09)
        _periods(c, prev)
        assert c["fail_streak"] == 1          # data refresh, not a print

    def test_changed_value_after_gap_is_new_period(self):
        prev = {"status": "fail", "value": 0.10, "fail_streak": 1,
                "streak_at": (date.today() - timedelta(days=95))
                .isoformat()}
        c = _check("fail", value=0.06)
        _periods(c, prev)
        assert c["fail_streak"] == 2

    def test_pass_resets_fail_streak(self):
        prev = {"status": "fail", "value": 0.10, "fail_streak": 2,
                "streak_at": (date.today() - timedelta(days=95))
                .isoformat()}
        c = _check("pass", value=0.30)
        _periods(c, prev)
        assert c["fail_streak"] == 0 and c["pass_streak"] == 1

    def test_unknown_carries_streaks_forward(self):
        prev = {"fail_streak": 2, "pass_streak": 0,
                "streak_at": "2025-01-01"}
        c = _check("unknown", value=None)
        _periods(c, prev)
        assert c["fail_streak"] == 2


# ---------- _hyp_status — the persistence ladder ---------------------

class TestHypStatusLadder:
    def test_single_period_hard_fail_is_warning_not_broken(self):
        checks = [_check("fail", hard=True, fail_streak=1),
                  _check("pass", metric="rev_accel", value=0.01)]
        assert _hyp_status(checks, {"rev_growth"}) == "deteriorating"

    def test_second_period_without_corroboration_is_severe(self):
        checks = [_check("fail", hard=True, fail_streak=2),
                  _check("pass", metric="rev_accel", value=0.01)]
        assert _hyp_status(checks, {"rev_growth"}) \
            == "severely_deteriorating"

    def test_second_period_with_corroboration_is_broken(self):
        checks = [_check("fail", hard=True, fail_streak=2),
                  _check("fail", metric="rev_accel", value=-0.10)]
        assert _hyp_status(checks, {"rev_growth"}) == "broken"

    def test_two_hard_fails_corroborate_each_other(self):
        checks = [_check("fail", metric="a", hard=True, fail_streak=2),
                  _check("fail", metric="b", hard=True, fail_streak=2)]
        assert _hyp_status(checks, {"a", "b"}) == "broken"

    def test_soft_fail_only_is_deteriorating(self):
        checks = [_check("fail", metric="rev_accel", value=-0.10),
                  _check("pass", hard=True, value=0.30)]
        assert _hyp_status(checks, {"rev_growth"}) == "deteriorating"

    def test_all_pass_on_track_and_unknown_neutral(self):
        assert _hyp_status(
            [_check("pass"), _check("pass", metric="b")], set()) \
            == "on_track"
        assert _hyp_status(
            [_check("unknown", value=None),
             _check("unknown", metric="b", value=None)], set()) \
            == "unknown"


# ---------- _rollup_status — criticality gates the symbol ------------

class TestRollup:
    def _hyp(self, status, crit="core", hard_fail=False, hid="h1"):
        return {"id": hid, "status": status, "criticality": crit,
                "hard_fail": hard_fail, "checks": []}

    def test_broken_core_breaks_symbol(self):
        assert _rollup_status([self._hyp("broken")], -2) == "broken"

    def test_broken_optional_cannot_break_symbol(self):
        hyps = [self._hyp("broken", crit="optional"),
                self._hyp("on_track", hid="h2"),
                self._hyp("on_track", hid="h3")]
        # optional death drags to deteriorating, never broken
        assert _rollup_status(hyps, 2) == "deteriorating"

    def test_core_hard_fail_is_severe_not_broken(self):
        hyps = [self._hyp("deteriorating", hard_fail=True),
                self._hyp("on_track", hid="h2")]
        assert _rollup_status(hyps, 1) == "severely_deteriorating"

    def test_optional_hard_fail_does_not_force_severe(self):
        hyps = [self._hyp("deteriorating", crit="optional",
                          hard_fail=True),
                self._hyp("on_track", hid="h2"),
                self._hyp("on_track", hid="h3")]
        assert _rollup_status(hyps, 3) == "improving"

    def test_all_unknown_stays_unknown(self):
        hyps = [self._hyp("unknown"), self._hyp("unknown", hid="h2")]
        assert _rollup_status(hyps, 0) == "unknown"


# ---------- coverage + stance -----------------------------------------

class TestCoverageAndStance:
    def test_core_coverage_ignores_optional_legs(self):
        hyps = [
            {"criticality": "core", "checks": [
                {"status": "pass"}, {"status": "unknown"}]},
            {"criticality": "optional", "checks": [
                {"status": "unknown"}, {"status": "unknown"},
                {"status": "unknown"}]},
        ]
        assert _core_coverage(hyps) == 0.5

    def test_severe_stance_is_review_not_avoid(self):
        s = stance_for("severely_deteriorating", 40.0, "uptrend")
        assert "under review" in s and "Avoid" not in s

    def test_broken_stance_unchanged(self):
        assert stance_for("broken", 40.0, "uptrend") == \
            "Avoid — thesis broken"
