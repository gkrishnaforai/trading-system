"""Reverse DCF — the growth rate today's price already assumes.

Forward DCF answers "what is it worth"; reverse DCF answers "what does
the market have to believe for this price to be fair". Solved as a
root-find over the SAME spec as the dcf_mega_cap builtin: 10 explicit
years, growth fading linearly to terminal over `fade_years`, Gordon
terminal, cash credited to equity, levered-FCF convention.

Deliberate deviation from the forward spec: the growth search is
UNCLAMPED below zero (forward clamps g0 >= 0 to avoid extrapolating
decline; inversion needs to express "the market prices a decline").
Bounds: [-0.60, growth_cap] — outside that, the answer is reported at
the bound with a boundary flag, not silently clamped into a plausible
middle.

Reference metric only — never blended into fair_value.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

_IMPLIED_LO = -0.60
_BISECT_ITERS = 60


def dcf_price(fcf_ttm: float, shares_outstanding: float,
              cash_and_equivalents: float, *, wacc: float,
              terminal_growth: float, growth: float, fade_years: float,
              explicit_years: int = 10,
              total_debt: float = 0.0,
              shares_diluted: Optional[float] = None) -> Dict[str, float]:
    """Same math as dsl.evaluator._eval_dcf_mega_cap_price — linear
    growth fade years 6-10, Gordon terminal, EV->equity bridge
    (+ cash − debt), diluted-share denominator when available — minus
    the g0 clamp and the terminal-share rejection (both are
    forward-discipline; inversion wants the raw answer plus the
    diagnostics)."""
    one_plus_wacc = 1.0 + wacc
    fade_den = max(1.0, float(fade_years))
    g_step = (growth - terminal_growth) / fade_den

    fcf = fcf_ttm
    pv_explicit = 0.0
    for t in range(1, explicit_years + 1):
        if t <= 5:
            g_t = growth
        else:
            g_t = growth - g_step * (t - 5)
        fcf = fcf * (1.0 + g_t)
        pv_explicit += fcf / math.pow(one_plus_wacc, t)

    terminal_value = (fcf * (1.0 + terminal_growth)) / (wacc - terminal_growth)
    pv_terminal = terminal_value / math.pow(one_plus_wacc, explicit_years)
    ev = pv_explicit + pv_terminal
    shares_eff = (float(shares_diluted)
                  if shares_diluted is not None and float(shares_diluted) > 0
                  else shares_outstanding)
    equity_value = ev + cash_and_equivalents - max(0.0, float(total_debt or 0.0))
    price = equity_value / shares_eff
    return {
        "price": price,
        "ev": ev,
        "terminal_share_of_ev": pv_terminal / ev if ev else float("nan"),
    }


def implied_growth(fcf_ttm: Optional[float], shares_outstanding: Optional[float],
                   cash_and_equivalents: Optional[float], spot: Optional[float],
                   *, wacc: float, terminal_growth: float, growth_cap: float,
                   fade_years: float, explicit_years: int = 10,
                   total_debt: Optional[float] = None,
                   shares_diluted: Optional[float] = None,
                   realized_growth: Optional[float] = None,
                   consensus_growth_pct_1y: Optional[float] = None) -> Dict[str, Any]:
    """Bisection-solve g such that dcf_price(g) = spot. f(g) is strictly
    increasing on the domain — 60 iterations nails it to ~1e-9."""
    base: Dict[str, Any] = {
        "status": "ok",
        "spec": {"wacc": wacc, "terminal_growth": terminal_growth,
                 "growth_cap": growth_cap, "fade_years": fade_years,
                 "explicit_years": explicit_years,
                 "growth_unclamped": True},
    }
    if not spot or spot <= 0:
        return {**base, "status": "not_applicable",
                "reason": "no_spot_price"}
    if not fcf_ttm or fcf_ttm <= 0:
        return {**base, "status": "not_applicable",
                "reason": "fcf_ttm_not_positive",
                "detail": "reverse DCF needs positive levered FCF — "
                          "pre-profit names have no cash stream to invert"}
    if not shares_outstanding or shares_outstanding <= 0:
        return {**base, "status": "not_applicable",
                "reason": "shares_not_positive"}
    if wacc - terminal_growth <= 0:
        return {**base, "status": "not_applicable",
                "reason": "wacc_lte_terminal_growth"}
    cash = float(cash_and_equivalents or 0.0)
    debt = float(total_debt or 0.0)

    def price_at(g: float) -> float:
        return dcf_price(fcf_ttm, shares_outstanding, cash, wacc=wacc,
                         terminal_growth=terminal_growth, growth=g,
                         fade_years=fade_years,
                         explicit_years=explicit_years,
                         total_debt=debt,
                         shares_diluted=shares_diluted)["price"]

    p_lo, p_hi = price_at(_IMPLIED_LO), price_at(growth_cap)
    base["spot"] = spot
    base["price_at_floor"] = round(p_lo, 4)
    base["price_at_cap"] = round(p_hi, 4)

    if spot <= p_lo:
        implied, boundary = _IMPLIED_LO, "below_floor"
    elif spot >= p_hi:
        implied, boundary = growth_cap, "at_cap"
    else:
        implied, boundary = None, None
        lo, hi = _IMPLIED_LO, growth_cap
        for _ in range(_BISECT_ITERS):
            mid = (lo + hi) / 2.0
            if price_at(mid) < spot:
                lo = mid
            else:
                hi = mid
        implied = (lo + hi) / 2.0

    base["implied_fcf_growth"] = round(implied, 4)
    base["boundary"] = boundary
    base["tv_share_at_implied"] = round(
        dcf_price(fcf_ttm, shares_outstanding, cash, wacc=wacc,
                  terminal_growth=terminal_growth, growth=implied,
                  fade_years=fade_years,
                  explicit_years=explicit_years,
                  total_debt=debt,
                  shares_diluted=shares_diluted)["terminal_share_of_ev"], 4)

    if realized_growth is not None:
        base["realized_growth"] = round(float(realized_growth), 4)
        base["gap_vs_realized"] = round(implied - float(realized_growth), 4)
    if consensus_growth_pct_1y is not None:
        cg = float(consensus_growth_pct_1y) / 100.0
        base["consensus_growth_1y"] = round(cg, 4)
        base["gap_vs_consensus_1y"] = round(implied - cg, 4)

    if boundary == "at_cap":
        base["flag"] = "implied_above_cap"
        base["note"] = (f"spot ${spot:.2f} needs >{growth_cap:.0%} FCF "
                        f"growth for a decade — beyond the model envelope")
    elif boundary == "below_floor":
        base["flag"] = "implied_below_floor"
        base["note"] = (f"spot ${spot:.2f} prices steeper decline than "
                        f"{_IMPLIED_LO:.0%}/yr — distress or a broken input")
    elif realized_growth is not None and implied > realized_growth + 0.10:
        base["flag"] = "implied_far_above_realized"
        base["note"] = (f"market prices {implied:.0%} FCF growth vs "
                        f"{realized_growth:.0%} realized — premium for "
                        "acceleration, not continuity")
    else:
        base["flag"] = None
    return base
