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

from .narratives import (ASSET_CLASS, FEAR_BANDS, KNIFE_BANDS,
                         STRUCTURAL)


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


def _weighted(parts: list[tuple[Optional[float], float, str, str]],
              min_coverage: float = 0.40
              ) -> tuple[Optional[int], list[str], list[dict]]:
    """Renormalize over available legs; report which were missing.
    Refuses to score below min_coverage — thin evidence stays thin.
    Returns (score, missing, details) — details carry the actual input
    value so the reason block shows evidence, not just a number."""
    live = [(s, w, n, v) for s, w, n, v in parts if s is not None]
    missing = [n for s, _, n, _ in parts if s is None]
    if not live or sum(w for _, w, _, _ in live) < min_coverage:
        return None, missing, []
    total = sum(w for _, w, _, _ in live)
    details = [{"name": n, "score": round(s), "weight": w, "value": v}
               for s, w, n, v in live]
    return round(sum(s * w for s, w, _, _ in live) / total), \
        missing, details


# --- per-metal fundamental score ------------------------------------------

def _v(m, k, fmt="{:+.2f}", suffix=""):
    """Reason-display for an input — the actual evidence value."""
    v = _f(m.get(k))
    return (fmt.format(v) + suffix) if v is not None else "—"


_FUNDAMENTAL_PARTS = {
    "gold": lambda m: [
        (_real_yield_score(_f(m.get("real_yield_chg20")),
                          _f(m.get("real_yield_level"))), .35,
         "real_yields",
         f"real yield {_v(m, 'real_yield_chg20')}pt/20d"
         + (f" (level {_v(m, 'real_yield_level', '{:.2f}')}%)"
            if _f(m.get("real_yield_level")) is not None else "")),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .25, "dollar",
         f"DXY {_v(m, 'dxy_chg20', '{:+.1f}')}%/20d"),
        (_f(m.get("liquidity_score")), .15, "liquidity",
         f"liquidity {_v(m, 'liquidity_score', '{:.0f}')}/100"),
        (_map(_f(m.get("hy_chg20")), -0.20, 0.80), .15,
         "credit_haven",
         f"HY spread {_v(m, 'hy_chg20')}pt/20d"),
        (float(STRUCTURAL["gold"]["structural_baseline"]), .10,
         "structural_demand", "CB/monetary demand (structural)"),
    ],
    "silver": lambda m: [
        (_real_yield_score(_f(m.get("real_yield_chg20")),
                          _f(m.get("real_yield_level"))), .15,
         "real_yields",
         f"real yield {_v(m, 'real_yield_chg20')}pt/20d"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .15, "dollar",
         f"DXY {_v(m, 'dxy_chg20', '{:+.1f}')}%/20d"),
        (_f(m.get("liquidity_score")), .10, "liquidity",
         f"liquidity {_v(m, 'liquidity_score', '{:.0f}')}/100"),
        (_map(_f(m.get("hy_chg20")), -0.20, 0.80), .10,
         "credit_haven", f"HY spread {_v(m, 'hy_chg20')}pt/20d"),
        (_map(_f(m.get("indpro_yoy")), -2.0, 3.0), .15, "growth",
         f"INDPRO {_v(m, 'indpro_yoy')}% yoy"),
        (_map(_f(m.get("gs_ratio_pctile")), 40.0, 90.0), .15,
         "gold_silver_ratio",
         f"G/S ratio {_v(m, 'gs_ratio_pctile', '{:.0f}')}th pctl/1y"),
        (float(STRUCTURAL["silver"]["structural_baseline"]), .15,
         "structural_demand",
         "solar + electronics + datacenter (structural)"),
        (_map(_f(m.get("breakeven_chg20")), -0.15, 0.15), .05,
         "inflation", f"breakevens {_v(m, 'breakeven_chg20')}pt/20d"),
    ],
    "copper": lambda m: [
        (_map(_f(m.get("indpro_yoy")), -2.0, 3.0), .30, "growth",
         f"INDPRO {_v(m, 'indpro_yoy')}% yoy"),
        (_map(_f(m.get("fxi_ret60")), -15.0, 15.0), .10,
         "china_proxy", f"FXI {_v(m, 'fxi_ret60', '{:+.1f}')}%/60d"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .15, "dollar",
         f"DXY {_v(m, 'dxy_chg20', '{:+.1f}')}%/20d"),
        (_f(m.get("liquidity_score")), .15, "liquidity",
         f"liquidity {_v(m, 'liquidity_score', '{:.0f}')}/100"),
        (_map(_f(m.get("hy_chg20")), 0.50, -0.20), .10,
         "credit_calm", f"HY spread {_v(m, 'hy_chg20')}pt/20d"),
        (_map(_f(m.get("breakeven_chg20")), -0.15, 0.15), .10,
         "inflation", f"breakevens {_v(m, 'breakeven_chg20')}pt/20d"),
        (float(STRUCTURAL["copper"]["structural_baseline"]), .10,
         "structural_demand",
         "grid + AI-datacenter power (structural)"),
    ],
    # --- crypto — liquidity legs dominate (it IS a liquidity asset),
    # credit_calm replaces gold's credit_haven: stress sells crypto,
    # it doesn't bid it
    "bitcoin": lambda m: [
        (_f(m.get("liquidity_score")), .30, "liquidity",
         f"liquidity {_v(m, 'liquidity_score', '{:.0f}')}/100"),
        (_real_yield_score(_f(m.get("real_yield_chg20")),
                          _f(m.get("real_yield_level"))), .20,
         "real_yields",
         f"real yield {_v(m, 'real_yield_chg20')}pt/20d"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .20, "dollar",
         f"DXY {_v(m, 'dxy_chg20', '{:+.1f}')}%/20d"),
        (_map(_f(m.get("hy_chg20")), 0.50, -0.20), .15,
         "credit_calm", f"HY spread {_v(m, 'hy_chg20')}pt/20d"),
        (float(STRUCTURAL["bitcoin"]["structural_baseline"]), .15,
         "structural_demand",
         "halving schedule + ETF bid (structural)"),
    ],
    "ethereum": lambda m: [
        (_f(m.get("liquidity_score")), .25, "liquidity",
         f"liquidity {_v(m, 'liquidity_score', '{:.0f}')}/100"),
        (_real_yield_score(_f(m.get("real_yield_chg20")),
                          _f(m.get("real_yield_level"))), .15,
         "real_yields",
         f"real yield {_v(m, 'real_yield_chg20')}pt/20d"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .15, "dollar",
         f"DXY {_v(m, 'dxy_chg20', '{:+.1f}')}%/20d"),
        (_map(_f(m.get("hy_chg20")), 0.50, -0.20), .15,
         "credit_calm", f"HY spread {_v(m, 'hy_chg20')}pt/20d"),
        (_map(_f(m.get("eth_btc_pctile")), 90.0, 20.0), .15,
         "eth_btc_ratio",
         f"ETH/BTC {_v(m, 'eth_btc_pctile', '{:.0f}')}th pctl/1y"),
        (float(STRUCTURAL["ethereum"]["structural_baseline"]), .15,
         "structural_demand",
         "staking + burn + L2 settlement (structural)"),
    ],
    "solana": lambda m: [
        (_f(m.get("liquidity_score")), .25, "liquidity",
         f"liquidity {_v(m, 'liquidity_score', '{:.0f}')}/100"),
        (_map(_f(m.get("dxy_chg20")), 2.0, -2.0), .15, "dollar",
         f"DXY {_v(m, 'dxy_chg20', '{:+.1f}')}%/20d"),
        (_map(_f(m.get("hy_chg20")), 0.60, -0.20), .20,
         "credit_calm", f"HY spread {_v(m, 'hy_chg20')}pt/20d"),
        (_real_yield_score(_f(m.get("real_yield_chg20")),
                          _f(m.get("real_yield_level"))), .10,
         "real_yields",
         f"real yield {_v(m, 'real_yield_chg20')}pt/20d"),
        (_map(_f(m.get("sol_btc_pctile")), 90.0, 20.0), .10,
         "sol_btc_ratio",
         f"SOL/BTC {_v(m, 'sol_btc_pctile', '{:.0f}')}th pctl/1y"),
        (float(STRUCTURAL["solana"]["structural_baseline"]), .20,
         "structural_demand",
         "network usage — weakest claim (structural)"),
    ],
}

ASSETS = list(_FUNDAMENTAL_PARTS)
METALS = [a for a in ASSETS if ASSET_CLASS[a] == "metals"]
CRYPTO = [a for a in ASSETS if ASSET_CLASS[a] == "crypto"]


def fundamental(metal: str, m: dict[str, Any]
                ) -> tuple[Optional[int], list[str], list[dict]]:
    return _weighted(_FUNDAMENTAL_PARTS[metal](m))


# --- fear / entry score ----------------------------------------------------

def fear(m: dict[str, Any], asset: str = "gold"
         ) -> tuple[Optional[int], list[str], list[dict]]:
    """m keys: off_52w_high_pct (neg), dist_sma200_pct (neg when
    below), rsi14. Bands are per asset class — a −30% drawdown is a
    regime event for gold but a routine correction for bitcoin."""
    dd_band, sma_band = FEAR_BANDS[ASSET_CLASS.get(asset, "metals")]
    dd = _map(_f(m.get("off_52w_high_pct")), 0.0, -dd_band)
    below = _f(m.get("dist_sma200_pct"))
    below_pts = _map(below, 0.0, -sma_band) if below is not None \
        and below < 0 else (0.0 if below is not None else None)
    rsi_pts = _map(_f(m.get("rsi14")), 50.0, 30.0)
    score, missing, details = _weighted(
        [(dd, .45, "drawdown",
          f"{_v(m, 'off_52w_high_pct', '{:.1%}')} off 52w high"),
         (below_pts, .25, "below_200sma",
          f"{_v(m, 'dist_sma200_pct', '{:.1%}')} vs 200SMA"),
         (rsi_pts, .35, "rsi",
          f"RSI {_v(m, 'rsi14', '{:.0f}')}")],
        min_coverage=0.50)
    if score is not None:
        score = min(100, score)
    return score, missing, details


def stabilization(m: dict[str, Any], asset: str = "gold"
                  ) -> tuple[Optional[bool], bool]:
    """(stabilized, falling_knife). Knife = deep washout still
    accelerating down — fear alone is never a buy. Stabilization is
    a turn signal, not a pause: RSI lifting off the low, price
    reclaiming the 20EMA, or a shallow 5d tape."""
    r5 = _f(m.get("ret5"))
    r20 = _f(m.get("ret20"))
    rsi = _f(m.get("rsi14"))
    rsi5 = _f(m.get("rsi14_5ago"))
    above20 = m.get("above_ema20")
    if rsi is None and r5 is None:
        return None, False
    k5, k20 = KNIFE_BANDS[ASSET_CLASS.get(asset, "metals")]
    knife = (rsi is not None and rsi < 35
             and (r5 or 0) < k5 and (r20 or 0) < k20)
    turning_up = ((rsi is not None and rsi5 is not None
                   and rsi - rsi5 >= 3)          # RSI lifting off low
                  or above20 is True)            # reclaimed the 20EMA
    stabilized = ((r5 is not None and r5 > -1.5)
                  or (rsi is not None and rsi >= 40)
                  or turning_up)
    return stabilized, knife


# --- verdict ----------------------------------------------------------------

def verdict(asset: str, f: Optional[int], e: Optional[int],
            regime: str, stabilized: Optional[bool],
            knife: bool) -> str:
    if f is None:
        return "no_score"
    # macro hard overlays — deflationary risk diagnoses copper/silver
    # recession, and crypto's version is risk_off: the same stress
    # that bids gold sells the liquidity assets first
    cls = ASSET_CLASS.get(asset, "metals")
    if regime == "deflationary_risk" and asset in ("copper", "silver") \
            and f < 70:
        return "reduce"
    if cls == "crypto" and regime in ("deflationary_risk", "risk_off") \
            and f < 75:
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


def verdict_reason(metal: str, v: str, f: Optional[int],
                   e: Optional[int], regime: str,
                   stab: Optional[bool], knife: bool) -> str:
    """Plain-English why — actual values, matching the research
    stance-reason convention."""
    fe = f"fundamentals {f} · fear {e if e is not None else '—'}"
    if v == "no_score":
        return "insufficient live data — legs under 40% coverage, " \
            "refusing to guess"
    if v == "strong_accumulate":
        return (f"{fe} — macro supportive AND deep discount with "
                "stabilization: the accumulation window")
    if v == "accumulate":
        return (f"{fe} — demand case intact while price is still "
                "discounted")
    if v == "watch_starter":
        return (f"{fe} — improving but neither leg fully lined up; "
                "starter-scale only")
    if v == "wait_for_pullback":
        return (f"{fe} — demand case intact but entry is extended; "
                "the metal needs a discount, not a chase")
    if v == "watch":
        if knife:
            return (f"{fe} — falling knife: deep washout still "
                    "accelerating, wait for stabilization")
        return f"{fe} — mixed evidence, no actionable alignment"
    if v == "wait":
        return f"{fe} — weak fundamentals; no thesis for a higher price"
    if v == "reduce":
        if regime == "deflationary_risk" and metal in ("copper",
                                                       "silver"):
            return (f"{fe} — deflationary-risk regime: demand "
                    "deteriorating under credit stress")
        if regime in ("risk_off", "deflationary_risk") and \
                ASSET_CLASS.get(metal) == "crypto":
            return (f"{fe} — risk-off regime: the liquidity assets "
                    "sell first; no accumulation until credit calms")
        return f"{fe} — demand case broken"
    return v


def opportunity(f: Optional[int], e: Optional[int]) -> Optional[int]:
    """Single display score — fundamentals-weighted so a great entry
    on a broken thesis never tops the board."""
    if f is None:
        return None
    return round(0.6 * f + 0.4 * (e or 0))


# --- transitions — "the turn just happened" detection ----------------------

_ACTIONABLE = {"accumulate", "strong_accumulate"}


def transitions(prev: Optional[dict], now: dict) -> dict[str, Any]:
    """Day-over-day journal delta — the 'time to start accumulating'
    signal. A state read says accumulate; a transition says the
    conditions JUST formed: regime flipped, verdict upgraded, or a
    metal's fundamental leg crossed actionable while fear is still
    elevated (price hasn't repriced yet)."""
    out: dict[str, Any] = {"as_of_prev": None, "macro_flipped": False,
                           "assets": {}}
    if not prev:
        out["first_run"] = True
        return out
    out["as_of_prev"] = prev.get("as_of")
    pl, nl = (prev.get("macro") or {}).get("label"), \
        (now.get("macro") or {}).get("label")
    out["macro_prev"], out["macro_now"] = pl, nl
    out["macro_flipped"] = bool(pl and nl and pl != nl)
    pl2 = (prev.get("macro") or {}).get("crypto_label")
    nl2 = (now.get("macro") or {}).get("crypto_label")
    out["crypto_label_prev"], out["crypto_label_now"] = pl2, nl2
    out["crypto_label_flipped"] = bool(pl2 and nl2 and pl2 != nl2)

    def _assets(p):
        a = dict(p.get("metals") or {})
        a.update(p.get("crypto") or {})
        return a
    pm, nm = _assets(prev), _assets(now)
    for metal, n in nm.items():
        p = pm.get(metal) or {}
        pv, nv = p.get("verdict"), n.get("verdict")
        f_now, f_prev = n.get("fundamental"), p.get("fundamental")
        e_now = n.get("fear")
        newly = (nv in _ACTIONABLE and pv not in _ACTIONABLE)
        crossed = (f_now is not None and f_prev is not None
                   and f_prev < 60 <= f_now
                   and (e_now or 0) >= 55)
        # upgraded = any non-actionable → actionable move, or the
        # fundamentals-just-turned + still-discounted window opening
        if pv == nv and not crossed:
            continue
        out["assets"][metal] = {
            "verdict_prev": pv, "verdict_now": nv,
            "newly_actionable": newly or crossed,
            "fundamental_delta": (f_now - f_prev
                                  if f_now is not None
                                  and f_prev is not None else None),
        }
    return out
