"""Deterministic per-dimension facts + scores.

Separates FACTS from INTERPRETATION: this module reduces the raw
snapshot numbers to labels and [-1, +1] scores the interpreter (LLM or
rules composer) reasons over. No LLM here — every label and score is
reproducible.

Score convention: +1 = strongly risk-supportive / improving,
-1 = strongly deteriorating. `change_score` is the weighted composite;
negative means the regime is degrading even if the primary label
stays bullish.
"""
from __future__ import annotations

from typing import Optional

from .models import DimensionFacts, MarketSnapshot

# deterioration composite: how fast the regime is weakening.
# trend is deliberately EXCLUDED — it answers "still bullish?" separately.
DETERIORATION_WEIGHTS = {
    "momentum": 0.25, "breadth": 0.25, "participation": 0.15,
    "volatility": 0.15, "macro": 0.10, "structure": 0.10,
}


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _sign(x: Optional[float]) -> int:
    if x is None or x == 0:
        return 0
    return 1 if x > 0 else -1


def derive_facts(snap: MarketSnapshot,
                 structural: Optional[dict] = None) -> DimensionFacts:
    t, m, b, v = snap.trend, snap.momentum, snap.breadth, snap.volatility
    p, ma, s = snap.participation, snap.macro, snap.structure
    drivers = []
    scores = {}

    # ---- trend ----
    if t.above_sma200 is False:
        trend = "bearish"
        drivers.append("price below SMA200")
    elif t.above_sma200 and t.above_sma50 and t.above_sma20:
        trend = "bullish"
        drivers.append("price above SMA20/50/200")
    elif t.above_sma200:
        trend = "bullish_weakening"
        drivers.append("price above SMA200 but below short MAs")
    else:
        trend = "mixed"
    if t.sma50_slope is not None and t.sma50_slope < 0:
        drivers.append(f"SMA50 slope negative ({t.sma50_slope:+.3f}%/day)")
    # persistence of the break — a poke below means little, a 3-day
    # hold under the 20EMA is a character change (their signal #1)
    if (t.days_below_ema20 or 0) >= 3:
        trend = ("bearish" if t.above_sma200 is False
                 else "bullish_weakening" if trend == "bullish"
                 else trend)
        drivers.append(f"SPY below 20EMA {t.days_below_ema20} straight "
                       f"days — persistence, not a poke")
    if (t.days_below_sma50 or 0) >= 2:
        drivers.append(f"SPY held under 50SMA {t.days_below_sma50} "
                       f"days — character changing")

    ts = 0.0
    for flag, w in ((t.above_sma200, 0.45), (t.above_sma50, 0.25),
                    (t.above_sma20, 0.10)):
        if flag is not None:
            ts += w if flag else -w
    ts += 0.10 * _sign(t.sma50_slope) + 0.05 * _sign(t.sma200_slope)
    if (t.days_below_ema20 or 0) >= 3:
        ts -= 0.10
    if (t.days_below_sma50 or 0) >= 3:
        ts -= 0.10
    scores["trend"] = round(_clamp(ts), 2)

    # ---- momentum ----
    r, dr = m.rsi14, m.rsi_5d_change
    if r is None:
        momentum = "unknown"
    elif r > 55 and (dr or 0) >= 0:
        momentum = "strong"
    elif r > 55 and (dr or 0) < 0:
        momentum = "weakening"
        drivers.append(f"RSI {r:.0f} falling ({dr:+.1f}/5d)")
    elif r < 45 and (dr or 0) > 0:
        momentum = "recovering"
        drivers.append(f"RSI {r:.0f} rising ({dr:+.1f}/5d)")
    elif r < 45:
        momentum = "weak"
        drivers.append(f"RSI {r:.0f} weak")
    elif (dr or 0) < -5:
        momentum = "weakening"
        drivers.append(f"RSI dropped {dr:+.1f} in 5d")
    else:
        momentum = "neutral"
    if m.macd_hist is not None and m.macd_hist < 0:
        drivers.append("MACD histogram negative")
    # absorption — where in the range the market closed. On a red
    # tape: closes near highs = buyers absorbing (normal dip);
    # closes near lows = sellers still in control (distribution tell)
    if m.close_loc_3d is not None:
        if m.close_loc_3d < 0.35 and (m.ret5 or 0) < 0:
            drivers.append(
                f"closing near lows (loc {m.close_loc_3d:.2f}/3d) — "
                f"sellers in control into the close")
        elif m.close_loc_3d > 0.60 and (m.ret5 or 0) < 0:
            drivers.append(
                f"dips absorbed at the close (loc "
                f"{m.close_loc_3d:.2f}/3d) — buyers showing up")

    ms = 0.0
    if r is not None:
        ms += _clamp((r - 50) / 50) * 0.5
    if dr is not None:
        ms += _clamp(dr / 10) * 0.3
    ms += 0.15 * _sign(m.macd_hist) + 0.10 * _sign(m.roc5)
    if m.close_loc_3d is not None:
        ms += _clamp((m.close_loc_3d - 0.5) * 0.4)
    scores["momentum"] = round(_clamp(ms), 2)

    # ---- breadth (trend-aware) ----
    b50, bchg5, bchg20 = b.pct_above_sma50, b.breadth_chg_5d, b.breadth_chg_20d
    if b50 is None:
        breadth = "unknown"
    elif (bchg5 or 0) <= -15 or (bchg20 or 0) <= -25:
        breadth = "deteriorating"
        drivers.append(f"breadth {b50:.0f}% collapsing "
                       f"({bchg5:+.1f}pts/5d, {bchg20:+.1f}pts/20d)")
    elif b50 >= 60 and (bchg5 or 0) >= 0:
        breadth = "strong"
    elif (bchg5 or 0) <= -3 or (bchg20 or 0) <= -10:
        breadth = "weakening"
        drivers.append(f"breadth {b50:.0f}% weakening "
                       f"({bchg5:+.1f}pts/5d, {bchg20:+.1f}pts/20d)")
    elif (bchg5 or 0) >= 10:
        breadth = "improving"
        drivers.append(f"breadth {b50:.0f}% and rising ({bchg5:+.1f}pts/5d)")
    elif b50 < 40:
        breadth = "weak"
        drivers.append(f"breadth weak at {b50:.0f}%")
    else:
        breadth = "neutral"
    if b.new_highs or b.new_lows:
        drivers.append(f"NH/NL {b.new_highs}/{b.new_lows}")
    # distribution divergence — new lows expanding while the index is
    # still near its highs is the classic early-distribution tell:
    # generals hold the index up while soldiers get shot
    if (b.new_lows > b.new_highs and b.new_lows >= 5
            and (s.dist_from_52w_high or -1) > -0.03):
        breadth = ("deteriorating" if breadth == "strong"
                   else "weakening" if breadth in ("neutral",
                                                 "improving")
                   else breadth)
        drivers.append("new lows expanding while SPY is within 3% of "
                       "highs — distribution divergence")

    bs = 0.0
    if b50 is not None:
        bs += _clamp((b50 - 50) / 50) * 0.4
    if bchg5 is not None:
        bs += _clamp(bchg5 / 20) * 0.3
    if bchg20 is not None:
        bs += _clamp(bchg20 / 30) * 0.3
    scores["breadth"] = round(_clamp(bs), 2)

    # ---- volatility (level x direction) ----
    vix, vxn = v.vix, v.vxn
    if vix is None and vxn is None:
        vol = "unknown"
    else:
        broad_level = ("low" if vix is not None and vix < 15 else "normal" if vix is not None and vix < 20
                       else "elevated" if vix is not None and vix < 28 else "high")
        tech_level = ("low" if vxn is not None and vxn < 20 else "normal" if vxn is not None and vxn < 28
                      else "elevated" if vxn is not None and vxn < 35 else "high")
        vol = broad_level if vix is not None else tech_level
        if vix is not None and v.vix_chg_5d is not None and v.vix_chg_5d > 1.5:
            vol = f"{broad_level}_rising"
            drivers.append(f"VIX {vix:.1f} rising ({v.vix_chg_5d:+.1f}/5d)")
        # fear acceleration — a single-day VIX spike large relative to
        # the index move is the "15 -> 22 on -1%" signature
        if (vix is not None and v.vix_chg_1d is not None
                and v.vix_chg_1d > 0
                and (v.vix_chg_1d >= 2.5
                     or v.vix_chg_1d / vix >= 0.15)):
            drivers.append(f"VIX jumped {v.vix_chg_1d:+.1f}pts in a "
                           f"day — fear accelerating")
        if vxn is not None and v.vxn_chg_5d is not None and v.vxn_chg_5d > 2:
            drivers.append(f"VXN {vxn:.1f} rising ({v.vxn_chg_5d:+.1f}/5d)")
        if broad_level in ("elevated", "high"):
            drivers.append(f"VIX {vix:.1f} {broad_level}")
        if tech_level in ("elevated", "high"):
            drivers.append(f"VXN {vxn:.1f} Nasdaq fear {tech_level}")
    if v.vix_term_ratio is not None and v.vix_term_ratio < 1:
        drivers.append("VIX term structure inverted (backwardation)")

    volatility_scores = []
    if vix is not None:
        broad_score = _clamp((20 - vix) / 20)
        if v.vix_chg_5d is not None:
            broad_score -= _clamp(v.vix_chg_5d / 10)
        volatility_scores.append(broad_score)
    if vxn is not None:
        tech_score = _clamp((28 - vxn) / 28)
        if v.vxn_chg_5d is not None:
            tech_score -= _clamp(v.vxn_chg_5d / 10)
        volatility_scores.append(tech_score)
    scores["volatility"] = round(_clamp(sum(volatility_scores) / len(volatility_scores)), 2) if volatility_scores else 0.0

    # ---- participation ----
    p50 = p.pct_sectors_above_sma50
    if p50 is None:
        participation = "unknown"
    else:
        rel = p.rel_strength_5d
        tech_weak = rel.get("QQQ", 0) < 0 and rel.get("SOXX", 0) < 0
        cyclical_ok = rel.get("IWM", 0) >= 0
        if p50 >= 70:
            participation = "broad"
        elif tech_weak and cyclical_ok:
            participation = "rotating"
            drivers.append("money rotating out of mega-cap tech")
        elif p50 < 45:
            participation = "narrow"
            drivers.append(f"only {p50:.0f}% of sectors above SMA50")
        else:
            participation = "narrow"

    ps = 0.0
    if p50 is not None:
        ps += _clamp((p50 - 50) / 50) * 0.5
    if p.rel_strength_5d:
        ps += _clamp(sum(p.rel_strength_5d.values())
                     / len(p.rel_strength_5d) / 0.05) * 0.5
    scores["participation"] = round(_clamp(ps), 2)

    # ---- macro (rates in bp, tiered risk-off) ----
    tnx = ma.instruments.get("us10y")
    dxy = ma.instruments.get("dxy")
    wti = ma.instruments.get("wti")
    signals = 0
    if tnx and tnx.delta5d is not None:
        bp = tnx.delta5d * 100   # ^TNX value is yield in %, delta*100 = bp
        if bp > 20:
            signals += 2
            drivers.append(f"10Y +{bp:.0f}bp/5d (sharp)")
        elif bp > 10:
            signals += 1
            drivers.append(f"10Y +{bp:.0f}bp/5d")
        elif bp < -15:
            drivers.append(f"10Y {bp:.0f}bp/5d (easing)")
    # 10Y absolute level — for a long-duration/high-multiple book the
    # discount rate's LEVEL caps multiples regardless of direction.
    # Calibration bands, not physics — revisit if the rate regime
    # drifts structurally (they were tuned when ~5.3% was hostile).
    if tnx and tnx.value is not None:
        if tnx.value >= 5.40:
            signals += 2
            drivers.append(f"10Y at {tnx.value:.2f}% — hostile to "
                           f"long-duration multiples")
        elif tnx.value >= 5.20:
            signals += 1
            drivers.append(f"10Y at {tnx.value:.2f}% — elevated "
                           f"discount rate")
    if dxy and dxy.chg5d is not None and dxy.chg5d > 0.01:
        signals += 1
        drivers.append("DXY strengthening")
    if wti and wti.chg5d is not None and wti.chg5d > 0.05:
        signals += 1
        drivers.append(f"oil {wti.chg5d:+.1%}/5d")
    # credit — junk vs IG spread proxy; when HYG lags LQD the bond
    # market is pricing risk before equities admit it
    hyg, lqd = ma.instruments.get("hyg"), ma.instruments.get("lqd")
    if hyg and lqd and hyg.chg5d is not None and lqd.chg5d is not None:
        cr = hyg.chg5d - lqd.chg5d
        if cr < -0.003:
            signals += 2
            drivers.append(f"credit stress — HYG vs LQD {cr:+.1%}/5d")
        elif cr < -0.001:
            signals += 1
            drivers.append(f"credit softening — HYG vs LQD {cr:+.1%}/5d")
    # breakevens proxy — TIP outperforming IEI = inflation repricing
    tip, iei = ma.instruments.get("tips"), ma.instruments.get("tsy13")
    if tip and iei and tip.chg5d is not None and iei.chg5d is not None:
        be = tip.chg5d - iei.chg5d
        if be > 0.004:
            signals += 1
            drivers.append(f"breakevens firming — TIP/IEI {be:+.1%}/5d")
    # tail-hedge demand — VVIX elevated means pros are buying tails
    vvix = ma.instruments.get("vvix")
    if vvix and vvix.value is not None and vvix.value > 110:
        signals += 1
        drivers.append(f"VVIX {vvix.value:.0f} — elevated tail hedging")
    if vix and vix > 25:
        signals += 2
    if not ma.instruments:
        macro = "unknown"
        mas = 0.0
    elif signals >= 3:
        macro = "risk_off"
    elif signals >= 2:
        macro = "mildly_risk_off"
    elif signals == 0 and (vix or 99) < 20:
        macro = "risk_on"
    else:
        macro = "neutral"
    scores["macro"] = round(_clamp(-signals / 3.0
                                   + (0.3 if macro == "risk_on" else 0)), 2)

    # ---- structure ----
    if s.spy_higher_high is None:
        structure = "unknown"
        ss = 0.0
    elif s.spy_higher_high and s.spy_higher_low:
        structure = "bullish"
        ss = 0.8
    elif not s.spy_higher_high and not s.spy_higher_low:
        structure = "bearish"
        drivers.append("SPY lower highs and lower lows")
        ss = -0.8
    elif s.spy_higher_high and not s.spy_higher_low:
        structure = ("under_pressure"
                     if breadth in ("weak", "weakening", "deteriorating")
                     else "bullish")
        ss = -0.3 if structure == "under_pressure" else 0.4
        if structure == "under_pressure":
            drivers.append("higher highs but lows slipping — distribution risk")
    else:
        structure = "recovering" if breadth == "improving" else "under_pressure"
        ss = 0.3 if structure == "recovering" else -0.3
    scores["structure"] = round(_clamp(ss), 2)

    # ---- structural layer — journaled slow monitors as drivers -----
    # Read-only context: capex cycle + FRED modules inform drivers and
    # confirmations, but do NOT enter the scores — the layer is too
    # young to calibrate weights against realized outcomes. Journal
    # first, weigh later.
    if structural is None:
        try:
            from . import structural as _struct
            structural = _struct.read()
        except Exception:
            structural = {}
    cx = (structural or {}).get("capex") or {}
    if cx.get("band") in ("serious_slowdown", "contraction"):
        drivers.append(
            f"capex cycle {cx['band'].replace('_', ' ')} — "
            f"{cx.get('n_elevated', '?')}/7 legs elevated")
    elif cx.get("band") == "slowing":
        drivers.append("capex cycle slowing — pacing deterioration")
    if (cx.get("d3m") or 0) >= 10:
        drivers.append(f"capex score +{cx['d3m']:.0f}pts/3m — "
                       f"deterioration accelerating")
    fred = (structural or {}).get("macro") or {}
    if (fred.get("overall") is not None and fred["overall"] < 40
            and (fred.get("age_days") or 0) <= 10):
        drivers.append(f"FRED macro composite {fred['overall']:.0f}"
                       f"/100 — weak")

    # Two transparent composites instead of one opaque blend:
    #   trend_score        = "is the market still bullish?"   (trend dim)
    #   deterioration_score = "is the regime weakening?"      (everything else)
    trend_score = scores.get("trend")
    det = sum(scores[d] * w for d, w in DETERIORATION_WEIGHTS.items()
              if d in scores)
    det_w = sum(w for d, w in DETERIORATION_WEIGHTS.items() if d in scores)
    deterioration_score = round(det / det_w, 2) if det_w else None

    return DimensionFacts(
        trend=trend, momentum=momentum, breadth=breadth,
        volatility=vol, participation=participation, macro=macro,
        structure=structure, scores=scores,
        trend_score=trend_score, deterioration_score=deterioration_score,
        drivers=drivers,
    )


def derive_confirmations(snap: MarketSnapshot,
                         structural: Optional[dict] = None
                         ) -> Dict[str, Dict[str, bool]]:
    """Actionable checklist — what would confirm a regime transition.

    Deterministic: each signal is a boolean evaluated from the snapshot.
    Reported to downstream agents as met/unmet so they can watch for the
    specific evidence that would flip the regime.
    """
    t, m, b, v, p, s = (snap.trend, snap.momentum, snap.breadth,
                        snap.volatility, snap.participation, snap.structure)
    tnx = snap.macro.instruments.get("us10y")
    if structural is None:
        try:
            from . import structural as _struct
            structural = _struct.read()
        except Exception:
            structural = {}
    st_cx = ((structural or {}).get("capex") or {}).get("alert")
    st_fred = (structural or {}).get("macro") or {}
    st_fred_weak = (st_fred.get("overall") is not None
                    and st_fred["overall"] < 40
                    and (st_fred.get("age_days") or 0) <= 10)

    bearish = {
        "SPY loses SMA50": t.above_sma50 is False,
        "SMA50 turns down": (t.sma50_slope or 0) < 0,
        "SPY below 20EMA 3+ days": (t.days_below_ema20 or 0) >= 3,
        "closes near day lows": (m.close_loc_3d or 1) < 0.35,
        "breadth < 40%": (b.pct_above_sma50 or 100) < 40,
        "new lows > new highs": b.new_lows > b.new_highs,
        "down-volume > up-volume": (b.up_volume_ratio or 1) < 0.5,
        "VIX > 20": (v.vix or 0) > 20,
        "VIX jumps in a day": (v.vix_chg_1d or 0) >= 2.5,
        "10Y ≥5.30%": (tnx.value if tnx else None) is not None
                      and tnx.value >= 5.30,
        "QQQ loses SMA50": s.qqq_above_sma50 is False,
        "semis make lower low": s.soxx_higher_low is False,
        "SPY >3% off 20d high": (s.dist_from_20d_high or 0) < -0.03,
        "structural: capex slowdown act-level": st_cx in ("act",
                                                         "confirmed"),
        "structural: FRED macro weak": bool(st_fred_weak),
    }
    bullish = {
        "SPY reclaims EMA20": (t.dist_ema20 or -1) > 0,
        "dips absorbed at close": (m.close_loc_3d or 0) >= 0.60,
        "breadth > 55%": (b.pct_above_sma50 or 0) > 55,
        "RSI > 50": (m.rsi14 or 0) > 50,
        "up-volume expands": (b.up_volume_ratio or 0) > 0.55,
        "QQQ leads SPY (5d)": (p.rel_strength_5d.get("QQQ") or -1) > 0,
        "semis stabilize (ret5 > 0)": (s.soxx_ret5 or -1) > 0,
        "10Y falls": (tnx.delta5d if tnx else None) is not None
                     and tnx.delta5d < 0,
        "10Y <5.20%": (tnx.value if tnx else None) is not None
                      and tnx.value < 5.20,
        "higher low confirmed": s.spy_higher_low is True,
    }
    return {"bearish_transition": bearish, "bullish_recovery": bullish}
