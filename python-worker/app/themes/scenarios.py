"""12-month macro scenarios — probabilities + per-theme sensitivity.

The point isn't forecasting; it's ranking under uncertainty:

    expected   = Σ P(scenario) × sensitivity(theme, scenario)
    downside   = same sum over the stress scenarios only — how the
                 theme holds if the tape breaks
    robustness = 100 − probability-weighted dispersion — a theme
                 attractive under every scenario ≠ a theme with one
                 lucky scenario and cliff risk elsewhere

Probabilities: curated priors tilted by the live regime stack —
forward_probs (20d bull/bear/chop), regime label, liquidity
direction/score, HY credit stress, real-yield trend. Each input
shifts a few points; priors dominate (honest — we don't pretend
to know the year).
"""
from __future__ import annotations

from typing import Any, Optional

from .narratives import SCENARIO_PRIORS, THEME_SENSITIVITY

SCENARIOS = list(SCENARIO_PRIORS)


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def probabilities(m: dict[str, Any]) -> dict[str, float]:
    """Tilt SCENARIO_PRIORS by live inputs. m keys: fwd_bull, fwd_bear
    (20d probs), regime, liquidity_score, liquidity_direction,
    hy_chg20 (points), real_yield_chg20 (points)."""
    p = dict(SCENARIO_PRIORS)
    bull, bear = _f(m.get("fwd_bull")), _f(m.get("fwd_bear"))
    liq_s, liq_d = _f(m.get("liquidity_score")), \
        m.get("liquidity_direction")
    hy_c = _f(m.get("hy_chg20"))
    ry_c = _f(m.get("real_yield_chg20"))

    if bull is not None and bull >= 40:
        p["growth_accel_falling_rates"] += 4
        p["growth_sticky_inflation"] += 2
        p["slowdown_falling_rates"] -= 3
    if bear is not None and bear >= 40:
        p["recession_stress"] += 6
        p["slowdown_falling_rates"] += 4
        p["growth_accel_falling_rates"] -= 5
        p["growth_sticky_inflation"] -= 4
    if liq_d == "improving" or (liq_s is not None and liq_s >= 65):
        p["growth_accel_falling_rates"] += 3
        p["recession_stress"] -= 3
    elif liq_d == "deteriorating" or (liq_s is not None
                                     and liq_s <= 35):
        p["slowdown_falling_rates"] += 3
        p["recession_stress"] += 4
        p["growth_accel_falling_rates"] -= 3
    if hy_c is not None and hy_c >= 0.30:          # credit stress rising
        p["recession_stress"] += 5
        p["growth_accel_falling_rates"] -= 3
        p["growth_sticky_inflation"] -= 2
    if ry_c is not None and ry_c <= -0.15:          # yields rolling over
        p["slowdown_falling_rates"] += 2
        p["growth_accel_falling_rates"] += 2
    reg = m.get("regime")
    if reg in ("defensive", "risk_off"):
        p["recession_stress"] += 4
        p["growth_sticky_inflation"] -= 3
    elif reg in ("aggressive", "strong_risk_on", "risk_on"):
        p["growth_accel_falling_rates"] += 3

    p = {k: max(3.0, v) for k, v in p.items()}     # floors — no
    total = sum(p.values())                         # scenario eliminated
    return {k: round(v / total * 100, 1) for k, v in p.items()}


def evaluate_theme(theme_key: str, probs: dict[str, float]
                   ) -> dict[str, Any]:
    """Expected/downside/robustness under the probability set."""
    sens = THEME_SENSITIVITY.get(theme_key) \
        or THEME_SENSITIVITY["_default"]
    expected = sum(probs[s] * sens[s] for s in probs) / 100.0
    stress = [s for s in probs if "recession" in s or "slowdown" in s]
    stress_p = sum(probs[s] for s in stress)
    downside = (sum(probs[s] * sens[s] for s in stress) /
                max(1.0, stress_p))
    mean = expected
    var = sum(probs[s] * (sens[s] - mean) ** 2 for s in probs) / 100.0
    dispersion = var ** .5
    robustness = max(0.0, 100.0 - dispersion * 2.5)
    return {"expected": round(expected, 1),
            "downside": round(downside, 1),
            "robustness": round(robustness, 1),
            "dispersion": round(dispersion, 1)}


def verdict(expected: Optional[float]) -> str:
    if expected is None:
        return "no_score"
    return ("strong" if expected >= 80 else
            "attractive" if expected >= 68 else
            "selective" if expected >= 55 else
            "watch" if expected >= 42 else "avoid")
