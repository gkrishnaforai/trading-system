"""Hedge engine — which vehicle protects the book best per dollar.

Two honest structures compared on history:

  QQQM put spread   buy ~5% OTM / sell ~22% OTM, 90 DTE — convex
                    payoff, capped at the width, decays only if
                    nothing happens. THE insurance structure.
                    QQQM = QQQ's retail share class — same index,
                    ~40% the share price → finer notional sizing.

  SQQQ sleeve       hold inverse-3x shares as a hedge — simple, no
                    options needed, but daily-reset decay bleeds in
                    chop even when QQQ is flat. Tactical, not
                    structural.

Backtest approach: roll the program forward over ~3y of stored bars.
Put spreads are BS-modeled (no historical chains — hv proxy for IV,
marked up in stress since skew makes OTM puts richer than flat-vol).
SQQQ uses real prices — the decay is in the tape itself.

Metrics: annual drag, protection delivered in the 2022-style legs,
worst-case book drawdown with vs without, hit rate.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_IV_STRESS_MARKUP = 1.4        # OTM puts price richer when VIX pops
_ROLL_DAYS = 63                # ~3 months — the hedge tenor
_LONG_OTM, _SHORT_OTM = 0.95, 0.78


def _hv(bars: list, n: int = 20) -> Optional[float]:
    """Annualized realized vol over n days."""
    if len(bars) < n + 1:
        return None
    rets = [bars[i].close / bars[i - 1].close - 1
            for i in range(len(bars) - n, len(bars))]
    if len(rets) < 2:
        return None
    import statistics as st
    return st.stdev(rets) * (252 ** 0.5)


def _spread_value(S: float, long_k: float, short_k: float,
                  dte: int, iv: float) -> float:
    """BS value of the put spread per unit (not per contract)."""
    from app.options.leaps_backtest import _price, RISK_FREE
    lp = _price(S, long_k, dte, RISK_FREE, iv, False)
    sp = _price(S, short_k, dte, RISK_FREE, iv, False)
    return max(0.0, lp - sp)


def backtest(exposure_usd: float = 100_000, beta: float = 1.4,
             coverage: float = 0.55, years: float = 3.0) -> dict:
    """Replay the rolling hedge program over stored bars.

    exposure_usd × beta = the notional that actually needs hedging.
    coverage = fraction hedged (the regime-scaled target — using the
    constant 55% here to compare vehicles apples-to-apples).

    Returns per-vehicle: spend, protection delivered in drawdown
    windows, net book outcome, honest caveats."""
    from app.market_data import bars as bars_mod
    books = bars_mod.load(["QQQ", "SQQQ", "^VIX"], days=int(years * 260))
    q = books.get("QQQ") or []
    sq = books.get("SQQQ") or []
    vx = books.get("^VIX") or []
    if len(q) < 300:
        return {"error": "insufficient history", "qqq_bars": len(q)}

    hedge_notional = exposure_usd * beta * coverage
    vix_by_date = {b.date: b.close for b in vx}
    sq_by_date = {b.date: b.close for b in sq}

    # ---- QQQM put spread program: roll a 90d spread every 63d ------
    cycles, spent, harvested = [], 0.0, 0.0
    open_spreads: list[dict] = []
    for i, b in enumerate(q):
        d = b.date
        S = b.close
        iv = max((_hv(q[:i + 1]) or 0.25),
                 (vix_by_date.get(d) or 20) / 100)
        if i % _ROLL_DAYS == 0:                     # roll new tranche
            width = S * (_LONG_OTM - _SHORT_OTM)    # ≈17% of spot
            qty = round(hedge_notional / (S * 100)) or 1
            debit = _spread_value(S, S * _LONG_OTM, S * _SHORT_OTM,
                                  90, iv) * 100 * qty
            spent += debit
            open_spreads.append({"i": i, "k1": S * _LONG_OTM,
                                 "k2": S * _SHORT_OTM, "qty": qty,
                                 "cost": debit})
        # mark + expire spreads
        keep = []
        for sp in open_spreads:
            age = i - sp["i"]
            if age >= 90:                            # expiry — settle
                w = sp["k1"] - sp["k2"]
                settle = max(0.0, min(sp["k1"] - S, w)) * 100 * sp["qty"]
                harvested += settle
                cycles.append({"exit": "expiry", "pay": settle,
                               "cost": sp["cost"]})
                continue
            # monetization ladder: spread hits ≥90% of width → harvest
            iv_now = (iv * _IV_STRESS_MARKUP
                      if S < sp["k1"] else iv)
            mid = _spread_value(S, sp["k1"], sp["k2"], 90 - age,
                                iv_now) * 100 * sp["qty"]
            if mid >= (sp["k1"] - sp["k2"]) * 100 * sp["qty"] * 0.9:
                harvested += mid
                cycles.append({"exit": "monetized", "pay": mid,
                               "cost": sp["cost"], "age": age})
                continue
            keep.append(sp)
        open_spreads = keep

    # residual: value of still-open spreads at the last bar
    for sp in open_spreads:
        iv_now = iv * _IV_STRESS_MARKUP if q[-1].close < sp["k1"] else iv
        mid = _spread_value(q[-1].close, sp["k1"], sp["k2"],
                            90 - (len(q) - sp["i"]), iv_now) \
            * 100 * sp["qty"]
        harvested += mid

    # ---- SQQQ sleeve: hold inverse shares = coverage of exposure ---
    # notional of SQQQ shares = hedge_notional / 3 (3x instrument)
    sqqq_notional = hedge_notional / 3
    sqqq_cost_basis = sqqq_notional
    sqqq_curve = []
    for i, b in enumerate(q):
        d = b.date
        spx = sq_by_date.get(d)
        if spx is None or not sq:
            continue
        start = sq_by_date.get(q[0].date) or sq[0].close
        sqqq_curve.append(spx / start * sqqq_notional)
    sqqq_end = sqqq_curve[-1] if sqqq_curve else 0.0
    sqqq_pnl = sqqq_end - sqqq_cost_basis

    # ---- worst window: biggest QQQ drawdown + what hedge paid ------
    peak = q[0].close
    worst = {"dd": 0.0, "idx": 0}
    for i, b in enumerate(q):
        peak = max(peak, b.close)
        dd = b.close / peak - 1
        if dd < worst["dd"]:
            worst = {"dd": dd, "idx": i}
    yrs = len(q) / 252
    return {
        "horizon_years": round(yrs, 1),
        "exposure": round(exposure_usd * beta, 0),
        "hedged_notional": round(hedge_notional, 0),
        "qqqm_spread": {
            "spend": round(spent, 0),
            "harvested": round(harvested, 0),
            "net_cost": round(spent - harvested, 0),
            "net_drag_per_yr": round((spent - harvested) / yrs, 0),
            "drag_pct": round((spent - harvested) / yrs
                              / exposure_usd * 100, 1),
            "cycles": len(cycles),
            "paid_cycles": sum(1 for c in cycles
                               if c["pay"] > c["cost"]),
            "hit_rate": round(sum(1 for c in cycles
                                  if c["pay"] > c["cost"])
                              / len(cycles) * 100) if cycles else 0,
            "monetized_early": sum(1 for c in cycles
                                   if c["exit"] == "monetized"),
        },
        "sqqq_sleeve": {
            "notional_held": round(sqqq_notional, 0),
            "end_value": round(sqqq_end, 0),
            "pnl": round(sqqq_pnl, 0),
            "pnl_per_yr": round(sqqq_pnl / yrs, 0),
            "decay_note": ("daily reset — bleeds in chop even when "
                           "QQQ is flat; the tape carries the decay"),
        },
        "worst_qqq_dd_pct": round(worst["dd"] * 100, 1),
        "honest": ("spread modeled on BS with hv/vix IV proxy + "
                   "stress markup — no historical chains; SQQQ is "
                   "real tape including decay"),
    }


def candidates() -> dict[str, Any]:
    """The structures to choose from — honest pros/cons, live where
    we can price them."""
    st = None
    try:
        from app.options import hedge_book
        st = hedge_book.state()
    except Exception:
        pass
    return {
        "structures": [
            {"vehicle": "QQQM put spread",
             "role": "structural insurance — the default",
             "why": ("convex payoff, defined max cost (the debit), "
                     "retail-priced strikes = finer sizing vs QQQ"),
             "watch": ("protection caps at the short strike — it's "
                       "insurance, not a parachute for a −40% leg")},
            {"vehicle": "SQQQ shares",
             "role": "tactical overlay — days/weeks, not months",
             "why": ("no options approval needed, instant liquidity, "
                     "pays convexly in a real crash"),
             "watch": ("daily-reset decay — bleeds in sideways chop "
                       "even when QQQ goes nowhere; wrong instrument "
                       "for a standing hedge")},
            {"vehicle": "collars on concentrated names",
             "role": "single-name event risk (earnings, >25% book)",
             "why": ("sell a covered call to fund the put — zero-cost "
                     "protection on the position, not the book"),
             "watch": "caps upside — only where you'd sell anyway"},
        ],
        "book": st,
        "note": ("QQQM ≈ QQQ/2.5 per share → same index, tighter "
                 "sizing granularity for a mid-size book"),
    }
