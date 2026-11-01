"""Per-metal scoring — pure functions, deterministic, testable.

Two scores per metal, deliberately kept separate:

  fundamental (0-100)  does the demand/monetary case support a higher
                       price once conditions normalize? Macro legs +
                       curated structural demand baseline.

  fear / entry (0-100) how discounted is the entry? Drawdown from 52w
                       high, distance below 200SMA, RSI washout.
                       High = fearful = the accumulation window we hunt
                       — but only when fundamentals stay intact.

Verdicts bind the two: strong fundamentals + high fear = accumulate;
strong fundamentals + low fear = wait_for_pullback (extended, not a
buy); broken fundamentals = reduce. A falling knife (high fear still
deteriorating, no stabilization) is capped at watch — fear alone is
never sufficient, matching the selloff engine's stabilization gate.
"""
from __future__ import annotations

from typing import Any, Optional

from .narratives import STRUCTURAL


def _f(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _map(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    """Linear 0-100 map: v<=lo -> 0, v>=hi -> 100."""
    if v is None:
        return None
    return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100.0))


# --- component scorers ----------------------------------------------------

def _real_yield_score(chg20: Optional[float],
                      level: Optional[float]) -> Optional[float]:
    """Falling real yields are THE metals repricing trigger."""
    s = _map(chg20, 0.20, -0.20)          # +0.20pt rise -> 0, fall -> 100
    if s is None:
        return None
    if level is not None:
        if level >= 2.2:
            s -= 10                      # high real-rate gravity
        elif level <= 1.0:
            s += 5
    return max(0.0, min(100.0, s))


def _weighted(parts: list[tuple[Optional[float], float, str]],
              min_coverage: float = 0.40
              ) -> tuple[Optional[int], list[str]]:
    """Renormalize over available legs; report which were missing.
    Refuses to score below min_coverage — thin evidence stays thin."""
    live = [(s, w) for s, w, _ in parts if s is not None]
    missing = [n for s, _, n in parts if s is None]
    if not live or sum(w for _, w in live) < min_coverage:
        return None, missing
    total = sum(w for _, w in live)
    return round(sum(s * w for s, w in live) / total), missing


# --- per-metal fundamental score ------------------------------------------

_FUNDAMENTAL_PARTS = {
    "gold": lambda m: [
        (_real_yield_score(_f(m.get("real_yield_chg20")),
                          _f(m.get("real_yield_level"))), .35,
         "real_yields"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .25, "dollar"),
        (_f(m.get("liquidity_score")), .15, "liquidity"),
        (_map(_f(m.get("hy_chg20")), -0.20, 0.80), .15,
         "credit_haven"),
        (float(STRUCTURAL["gold"]["structural_baseline"]), .10,
         "structural_demand"),
    ],
    "silver": lambda m: [
        (_real_yield_score(_f(m.get("real_yield_chg20")),
                          _f(m.get("real_yield_level"))), .15,
         "real_yields"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .15, "dollar"),
        (_f(m.get("liquidity_score")), .10, "liquidity"),
        (_map(_f(m.get("hy_chg20")), -0.20, 0.80), .10,
         "credit_haven"),
        (_map(_f(m.get("indpro_yoy")), -2.0, 3.0), .15, "growth"),
        (_map(_f(m.get("gs_ratio_pctile")), 40.0, 90.0), .15,
         "gold_silver_ratio"),
        (float(STRUCTURAL["silver"]["structural_baseline"]), .15,
         "structural_demand"),
        (_map(_f(m.get("breakeven_chg20")), -0.15, 0.15), .05,
         "inflation"),
    ],
    "copper": lambda m: [
        (_map(_f(m.get("indpro_yoy")), -2.0, 3.0), .30, "growth"),
        (_map(_f(m.get("fxi_ret60")), -15.0, 15.0), .10,
         "china_proxy"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .15, "dollar"),
        (_f(m.get("liquidity_score")), .15, "liquidity"),
        (_map(_f(m.get("hy_chg20")), 0.50, -0.20), .10,
         "credit_calm"),
        (_map(_f(m.get("breakeven_chg20")), -0.15, 0.15), .10,
         "inflation"),
        (float(STRUCTURAL["copper"]["structural_baseline"]), .10,
         "structural_demand"),
    ],
}

METALS = list(_FUNDAMENTAL_PARTS)


def fundamental(metal: str, m: dict[str, Any]
                ) -> tuple[Optional[int], list[str]]:
    return _weighted(_FUNDAMENTAL_PARTS[metal](m))


# --- fear / entry score ----------------------------------------------------

def fear(m: dict[str, Any]) -> tuple[Optional[int], list[str]]:
    """m keys: off_52w_high_pct (neg), dist_sma200_pct (neg when
    below), rsi14."""
    dd = _map(_f(m.get("off_52w_high_pct")), 0.0, -0.30)
    below = _f(m.get("dist_sma200_pct"))
    below_pts = _map(below, 0.0, -0.20) if below is not None \
        and below < 0 else (0.0 if below is not None else None)
    rsi_pts = _map(_f(m.get("rsi14")), 50.0, 30.0)
    score, missing = _weighted([(dd, .45, "drawdown"),
                                (below_pts, .25, "below_200sma"),
                                (rsi_pts, .35, "rsi")],
                               min_coverage=0.50)
    if score is not None:
        score = min(100, score)
    return score, missing


def stabilization(m: dict[str, Any]) -> tuple[Optional[bool], bool]:
    """(stabilized, falling_knife). Knife = deep washout still
    accelerating down — fear alone is never a buy."""
    r5 = _f(m.get("ret5"))
    r20 = _f(m.get("ret20"))
    rsi = _f(m.get("rsi14"))
    if rsi is None or r5 is None:
        return None, False
    knife = rsi < 35 and (r5 or 0) < -4.0 and (r20 or 0) < -5.0
    stabilized = (r5 > -1.5) or (rsi >= 40)
    return stabilized, knife


# --- verdict ----------------------------------------------------------------

def verdict(metal: str, f: Optional[int], e: Optional[int],
            regime: str, stabilized: Optional[bool],
            knife: bool) -> str:
    if f is None:
        return "no_score"
    # macro hard overlay — deflationary risk diagnoses copper/silver
    # recession, not accumulation
    if regime == "deflationary_risk" and metal in ("copper", "silver") \
            and f < 70:
        return "reduce"
    if knife and f < 75:
        return "watch"            # don't catch a falling knife
    e = e or 0
    if f >= 75 and e >= 65 and stabilized is not False:
        return "strong_accumulate"
    if f >= 60 and e >= 55:
        return "accumulate"
    if f >= 55:
        return "wait_for_pullback" if e < 40 else "watch_starter"
    if f >= 45:
        return "watch"
    if f >= 30:
        return "wait"
    return "reduce"


def opportunity(f: Optional[int], e: Optional[int]) -> Optional[int]:
    """Single display score — fundamentals-weighted so a great entry
    on a broken thesis never tops the board."""
    if f is None:
        return None
    return round(0.6 * f + 0.4 * (e or 0))
