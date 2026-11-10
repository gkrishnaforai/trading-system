"""Smoke tests for the pure math in this session's new engines —
guidance_intel normalize, earnings_quality flag logic, flow
CLV/streak classification. Synthetic inputs, no DB, no network.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_guidance_normalize_direction_and_period():
    from app.signals.guidance_intel import _normalize
    n = _normalize("Vistra raised its 2026 Ongoing Operations "
                   "Adjusted EBITDA guidance to $7.1 billion")
    assert n["direction"] == "raised"
    assert n["metric"] == "margin"
    assert n["period"] == "fy2026"
    n2 = _normalize("lowered full-year revenue outlook")
    assert n2["direction"] == "lowered"
    # unparsed stays unparsed — never guessed
    n3 = _normalize("the company held a conference")
    assert n3["direction"] is None and not n3["normalized"]


def test_guidance_num_regex_never_bare_dot():
    """The float('.') crash — _NUM must require a leading digit."""
    from app.signals.guidance_intel import _normalize
    n = _normalize("guidance. for the period .")
    for v, _u in n["values"]:
        assert v == v  # no NaN/parse crash


def test_eq_growth_uses_abs_denominator():
    """Negative prev-year base must not flip growth sign."""
    from app.signals.earnings_quality import _growth, _map
    assert _growth(50, -100) == 1.5          # +150% swing
    assert _growth(-50, 100) == -1.5
    assert _growth(None, 5) is None
    # _map bounds: mid maps ~50, edges clamp 0/100
    assert _map(0.0, -0.1, 0.1) == 50.0
    assert _map(9.0, -0.1, 0.1) == 100.0
    assert _map(-9.0, -0.1, 0.1) == 0.0


def test_flow_clv_math():
    """CLV formula sanity — close-at-highs +1, at-lows -1,
    degenerate range returns None not a crash."""
    from app.signals.flow_footprint import _clv
    bar = lambda c, h=110.0, l=100.0: {"high": h, "low": l,
                                       "close": c}
    assert abs(_clv(bar(110.0)) - 1.0) < 1e-9
    assert abs(_clv(bar(100.0)) + 1.0) < 1e-9
    assert abs(_clv(bar(105.0))) < 1e-9
    # degenerate range — returns None, never divides by zero
    assert _clv({"high": 105.0, "low": 105.0, "close": 105.0})         is None
