"""Liquidity & new-money flow monitor — how aggressive can we be.

Not 'is the Fed balance sheet big' — whether financial conditions are
BECOMING more supportive and whether that liquidity is actually
reaching equities. Three separations the spec demands:

  system liquidity  WALCL / TGA / RRP / reserves — money in the pipes
  credit conditions HY spreads + NFCI            — price of risk
  equity transmission  breadth + SMH/QQQ relative strength — did it
                       reach stocks (real fund-flow series aren't on
                       FRED; we say proxy, not flows)

Score = 7 weighted components (spec weights), each 0-100 from its own
change/trend — level says nothing, DELTA is the signal. Missing series
→ component excluded and weights renormalized; coverage surfaced.
PIT: every snapshot journals the observation_date per series so a
replay sees what was actually known.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Optional

from app.signals.correction_alarms import _fred_series

logger = logging.getLogger(__name__)

# (component, weight, series, obs-back, invert)
# invert=True → a FALLING series is the positive leg (TGA/RRP drawdown
# releases reserves; HY narrowing = easing conditions)
_COMPONENTS = [
    ("fed_balance_sheet", 20, "WALCL",      4,  False),
    ("tga",               15, "WTREGEN",    4,  True),
    ("reverse_repo",      10, "RRPONTSYD", 20,  True),
    ("bank_reserves",      8, "WRESBAL",    4,  False),
    ("bank_credit",        7, "TOTBKCR",    4,  False),
    ("credit_conditions", 15, "BAMLH0A0HYM2", 20, True),
]

_BUCKETS = [(80, "strong_expansion"), (65, "expansion"),
            (45, "neutral"), (25, "tightening"), (0, "severe")]

# ETF flow groups — where money is going, not just whether it left.
# Price/RS is a PROXY for flows (real creations/redemptions need a
# paid feed); grouped so a defensive bid reads differently from a
# risk bid. Order = defensive → risk for the destination label.
_FLOW_GROUPS = {
    "cash_duration": ["BIL", "SHY", "IEF", "TLT"],
    "gold":          ["GLD", "IAU", "SLV"],
    "broad_equity":  ["SPY", "VOO", "RSP"],
    "small_cap":     ["IWM", "IJR"],
    "growth_tech":   ["QQQ", "IGV"],
    "semis_ai":      ["SMH", "SOXX"],
    "crypto":        ["IBIT", "BITO"],
}
_RISK_GROUPS = ("broad_equity", "small_cap", "growth_tech",
                "semis_ai", "crypto")
_SAFE_GROUPS = ("cash_duration", "gold")


def _pct_chg(pts: list[tuple[date, float]], back: int) -> Optional[float]:
    """% change over `back` observations — weekly series: back=4 ≈
    1 month; daily: back=20."""
    if len(pts) < back + 1:
        return None
    a, b = pts[-back - 1][1], pts[-1][1]
    if not a:
        return None
    return (b - a) / abs(a)


def _band(chg: Optional[float], invert: bool) -> Optional[int]:
    """Change → 0-100. Calibrated to the recent QT/QE range: ±2% is
    a strong impulse for stock series; the spec's 'expansion' starts
    meaningfully above zero."""
    if chg is None:
        return None
    x = -chg if invert else chg
    if x >= 0.02:
        return 90
    if x >= 0.005:
        return 75
    if x >= 0:
        return 60
    if x >= -0.005:
        return 40
    if x >= -0.02:
        return 25
    return 10


def _nfci() -> Optional[int]:
    """NFCI level — negative = looser than average. Level-based, the
    one component where level IS the state."""
    pts = _fred_series("NFCI", days=120)
    if not pts:
        return None
    v = pts[-1][1]
    if v <= -0.6:
        return 90
    if v <= -0.3:
        return 75
    if v <= 0:
        return 60
    if v <= 0.3:
        return 40
    return 20


# HY spread LEVEL bands (percent) — the anchor the change signal
# lacks: 3.3% widening off 3.0 is noise, 6%+ is stress at any delta.
_HY_LEVEL = [(3.0, 85), (3.5, 75), (4.0, 65), (5.0, 45), (6.0, 30)]

# RRPONTSYD in $B — below this the facility is effectively empty:
# nothing left to drain OR release, so tiny changes are noise.
_RRP_DEPLETED_B = 75.0


def _hy_level(v: Optional[float]) -> Optional[int]:
    if v is None:
        return None
    for thr, sc in _HY_LEVEL:
        if v <= thr:
            return sc
    return 15


def _equity_legs() -> dict[str, Any]:
    """Transmission proxies — NOT fund flows (no FRED feed): universe
    breadth internals + semiconductor/growth relative strength vs
    SPY from canonical daily_bars."""
    out: dict[str, Any] = {}
    try:
        from app.signals import breadth as _b
        out["breadth"] = _b.universe_internals()
    except Exception as exc:
        logger.debug("liq breadth: %s", exc)
        out["breadth"] = {}
    try:
        from app.database import db
        rows = db.execute_query(
            "SELECT symbol, close FROM daily_bars"
            " WHERE symbol IN ('SPY','QQQ','SMH','IWM')"
            " AND date > (SELECT max(date) FROM daily_bars) - 40"
            " ORDER BY date")
        px: dict[str, list[float]] = {}
        for r in rows:
            px.setdefault(r["symbol"], []).append(float(r["close"]))
        spy = px.get("SPY")
        out["rel_1m"] = {}
        if spy and len(spy) >= 22:
            spy_r = spy[-1] / spy[-22] - 1
            for etf in ("QQQ", "SMH", "IWM"):
                s = px.get(etf)
                if s and len(s) >= 22:
                    out["rel_1m"][etf] = round(
                        (s[-1] / s[-22] - 1) - spy_r, 4)
    except Exception as exc:
        logger.debug("liq rel strength: %s", exc)
    return out


def _flow_matrix() -> dict[str, Any]:
    """The reviewer's core question — where is money going? 5d and
    ~1m (21-bar) returns per ETF group + relative strength vs SPY.
    A defensive group leading while risk lags = withdrawal into
    safety; semis leading = deployment; all falling together =
    deleveraging, not rotation."""
    try:
        from app.database import db
        syms = sorted({s for syms_ in _FLOW_GROUPS.values()
                      for s in syms_} | {"SPY"})
        rows = db.execute_query(
            "SELECT symbol, date, close FROM daily_bars"
            " WHERE symbol = ANY(:s)"
            " AND date > (SELECT max(date) FROM daily_bars) - 45"
            " ORDER BY symbol, date", {"s": syms})
    except Exception as exc:
        logger.debug("liq flow matrix: %s", exc)
        return {"groups": {}, "destination": None}
    px: dict[str, list[float]] = {}
    dates: dict[str, str] = {}
    for r in rows:
        px.setdefault(r["symbol"], []).append(float(r["close"]))
        dates[r["symbol"]] = str(r["date"])
    groups: dict[str, dict] = {}
    spy = px.get("SPY") or []
    spy_5d = spy[-1] / spy[-6] - 1 if len(spy) >= 6 else None
    spy_1m = spy[-1] / spy[-22] - 1 if len(spy) >= 22 else None
    for g, syms_ in _FLOW_GROUPS.items():
        r5, r1 = [], []
        for s in syms_:
            b = px.get(s) or []
            if len(b) >= 6:
                r5.append(b[-1] / b[-6] - 1)
            if len(b) >= 22:
                r1.append(b[-1] / b[-22] - 1)
        if not r5 and not r1:
            continue
        groups[g] = {
            "ret_5d": round(sum(r5) / len(r5), 4) if r5 else None,
            "ret_1m": round(sum(r1) / len(r1), 4) if r1 else None,
            "rs_spy_5d": (round(sum(r5) / len(r5) - spy_5d, 4)
                        if r5 and spy_5d is not None else None),
            "rs_spy_1m": (round(sum(r1) / len(r1) - spy_1m, 4)
                        if r1 and spy_1m is not None else None),
            "n": len(set(syms_) & set(px)),
        }
    # destination — the group with the best 5d relative move, labeled
    dest = None
    scored = [(g, v["rs_spy_5d"] if v["rs_spy_5d"] is not None
               else v["ret_5d"]) for g, v in groups.items()
              if (v.get("rs_spy_5d") or v.get("ret_5d")) is not None]
    if scored:
        top = max(scored, key=lambda t: t[1])
        risk_ret = [groups[g]["ret_5d"] for g in _RISK_GROUPS
                    if groups.get(g, {}).get("ret_5d") is not None]
        safe_rs = [groups[g]["rs_spy_5d"] for g in _SAFE_GROUPS
                   if groups.get(g, {}).get("rs_spy_5d") is not None]
        all_risk_down = bool(risk_ret) and all(r < 0 for r in risk_ret)
        if all_risk_down and safe_rs and all(v > 0 for v in safe_rs):
            dest = "deleveraging_to_safety"
        elif top[0] in _SAFE_GROUPS and top[1] > 0:
            dest = "rotation_to_safety"
        elif top[0] == "semis_ai" and top[1] > 0:
            dest = "deployment_ai_semis"
        elif top[0] in _RISK_GROUPS and top[1] > 0:
            dest = "deployment_equities"
        elif all_risk_down and (not safe_rs
                                or all(v <= 0 for v in safe_rs)):
            dest = "broad_outflow"
        else:
            dest = "mixed_rotation"
    return {"groups": groups, "destination": dest,
            "spy_5d": round(spy_5d, 4) if spy_5d is not None else None,
            "bar_date": dates.get("SPY")}


def _credit_depth() -> dict[str, Any]:
    """Credit beyond HY: IG spreads + VIX — the reviewer's credit
    stress leg deepened. HY widening + IG widening + VIX elevated =
    real stress; HY alone can be sector noise."""
    out: dict[str, Any] = {}
    ig = _fred_series("BAMLC0A0CM", days=120)      # IG OAS, daily
    if ig:
        igc = _pct_chg(ig, 20)
        out["ig_oas"] = round(ig[-1][1], 2)
        out["ig_chg_20d"] = round(igc, 4) if igc is not None else None
        out["ig_obs"] = str(ig[-1][0])
        # IG level bands are tighter than HY: <1.2 calm, >2.0 stress
        v = ig[-1][1]
        out["ig_score"] = (90 if v <= 1.0 else 75 if v <= 1.3 else
                           60 if v <= 1.6 else 40 if v <= 2.0 else 20)
    vx = _fred_series("VIXCLS", days=60)
    if vx:
        out["vix"] = round(vx[-1][1], 1)
        out["vix_obs"] = str(vx[-1][0])
        v = vx[-1][1]
        out["vix_score"] = (90 if v <= 14 else 75 if v <= 18 else
                            60 if v <= 22 else 40 if v <= 28 else
                            20 if v <= 35 else 10)
    sc = [s for s in (out.get("ig_score"), out.get("vix_score"))
          if s is not None]
    out["credit_depth_score"] = (round(sum(sc) / len(sc))
                               if sc else None)
    return out


def _recovery_sequence(comps: list[dict], flow: dict,
                       breadth: dict) -> dict[str, Any]:
    """The 5-step confirmation ladder from the spec — each step a
    bool computed from legs already computed; a partial sequence is
    journaled, never forced to a verdict."""
    get = lambda n: next((c for c in comps if c["name"] == n), {})
    hy = get("credit_conditions")
    hy_chg = hy.get("chg_pct")
    groups = flow.get("groups") or {}
    semis = groups.get("semis_ai") or {}
    broad = groups.get("broad_equity") or {}
    p50 = breadth.get("pct_above_50")
    steps = [
        {"step": "credit_stabilizes",
         "met": (hy_chg is not None and hy_chg <= 0.005),
         "detail": f"HY Δ {round(hy_chg*100,2)}%" if hy_chg is not None
                  else "no HY data"},
        {"step": "outflows_slow",
         "met": (broad.get("ret_5d") is not None
                 and broad["ret_5d"] >= -0.01),
         "detail": (f"broad 5d {round(broad['ret_5d']*100,1)}%"
                    if broad.get("ret_5d") is not None
                    else "no broad-equity bars")},
        {"step": "semis_lead",
         "met": (semis.get("rs_spy_5d") is not None
                 and semis["rs_spy_5d"] > 0),
         "detail": (f"SMH grp RS {round(semis['rs_spy_5d']*100,1)}%"
                    if semis.get("rs_spy_5d") is not None
                    else "no semis bars")},
        {"step": "breadth_improves",
         "met": isinstance(p50, (int, float)) and p50 >= 45,
         "detail": (f"{round(p50)}% > 50dma" if isinstance(p50,
                    (int, float)) else "no breadth")},
        {"step": "risk_groups_bid",
         "met": (sum(1 for g in _RISK_GROUPS
                     if (groups.get(g) or {}).get("ret_5d", -1) > 0)
                 >= 2),
         "detail": "≥2 risk groups positive 5d"},
    ]
    met = sum(1 for s in steps if s["met"])
    return {"steps": steps, "met": met, "of": len(steps),
            "recovery_score": round(met / len(steps) * 100)}


def _equity_score(legs: dict) -> tuple[Optional[int], Optional[int]]:
    """(fund-flows-proxy score, breadth score) — each 0-100 or None."""
    rel = (legs.get("rel_1m") or {})
    breadth = legs.get("breadth") or {}
    bs = breadth.get("breadth_score")
    bs_score = int(max(0, min(100, round(bs)))) \
        if isinstance(bs, (int, float)) else None
    # relative-strength → score: +3% vs SPY = leadership = 85
    vals = [v for v in rel.values() if isinstance(v, (int, float))]
    flow, character = None, None
    if vals:
        pos = sum(1 for v in vals if v > 0)
        character = ("broad_inflows" if pos == len(vals) else
                     "broad_outflows" if pos == 0 else "rotation")
        m = sum(vals) / len(vals)
        flow = 90 if m >= 0.03 else 75 if m >= 0.01 else \
            60 if m >= 0 else 40 if m >= -0.01 else \
            25 if m >= -0.03 else 10
        if character == "rotation":
            # mixed leadership = repositioning, not money leaving —
            # tech-led strength vs broad weakness floors the read
            flow = max(flow, 40)
    return flow, bs_score, character


def evaluate() -> dict[str, Any]:
    """Compute the state — no journal (run() wraps it)."""
    comps = []
    obs_dates: dict[str, str] = {}
    for name, w, sid, back, inv in _COMPONENTS:
        pts = _fred_series(sid, days=220)
        chg = _pct_chg(pts, back)
        comp = {"name": name, "weight": w, "series": sid,
                "chg_pct": round(chg, 4) if chg is not None else None,
                "score": _band(chg, inv)}
        if pts:
            comp["obs"] = str(pts[-1][0])
            comp["obs_age"] = (date.today() - pts[-1][0]).days
            obs_dates[sid] = comp["obs"]
        if name == "credit_conditions" and pts:
            # level-anchored: a modest widening off a tight base is
            # not stress — level 60% / change 40%
            lvl = _hy_level(pts[-1][1])
            if lvl is not None and comp["score"] is not None:
                comp["score"] = round(0.6 * lvl + 0.4 * comp["score"])
                comp["level"] = round(pts[-1][1], 2)
        if name == "reverse_repo" and pts \
                and pts[-1][1] < _RRP_DEPLETED_B:
            # facility near-empty — nothing left to drain or release;
            # tiny changes around zero are noise, not contraction
            comp["score"] = 40
            comp["note"] = "facility depleted"
        comps.append(comp)
    nfci = _nfci()
    comps.append({"name": "financial_conditions", "weight": 0,
                  "series": "NFCI", "score": nfci,
                  "note": "level, part of credit leg"})
    credit_x = _credit_depth()
    if credit_x.get("ig_score") is not None:
        comps.append({"name": "ig_spread", "weight": 0,
                      "series": "BAMLC0A0CM",
                      "score": credit_x["ig_score"],
                      "level": credit_x.get("ig_oas"),
                      "obs": credit_x.get("ig_obs"),
                      "note": "IG OAS — credit leg, level-scored"})
    if credit_x.get("vix_score") is not None:
        comps.append({"name": "vix_level", "weight": 0,
                      "series": "VIXCLS",
                      "score": credit_x["vix_score"],
                      "level": credit_x.get("vix"),
                      "obs": credit_x.get("vix_obs"),
                      "note": "fear leg — level, unscored in headline"})
    legs = _equity_legs()
    flow = _flow_matrix()
    flow_sc, breadth_sc, flow_char = _equity_score(legs)
    comps.append({"name": "equity_flows_proxy", "weight": 15,
                  "series": "SMH/QQQ/IWM vs SPY",
                  "score": flow_sc,
                  "note": flow_char,
                  "rel_1m": legs.get("rel_1m")})
    comps.append({"name": "market_breadth", "weight": 10,
                  "series": "universe internals",
                  "score": breadth_sc,
                  "pct_above_50": (legs.get("breadth") or {})
                  .get("pct_above_50")})

    scored = [c for c in comps if c.get("score") is not None
              and c["weight"] > 0]
    wsum = sum(c["weight"] for c in scored)
    score = round(sum(c["score"] * c["weight"] for c in scored)
                  / wsum) if wsum else None
    total_w = sum(c["weight"] for c in comps)
    coverage = round(wsum / total_w, 2) if total_w else 0.0
    band = next((b for thr, b in _BUCKETS
                 if score is not None and score >= thr), None)

    def impulse(*names: str) -> str:
        scs = [c["score"] for c in comps
               if c["name"] in names and c.get("score") is not None]
        if not scs:
            return "unknown"
        m = sum(scs) / len(scs)
        return "expanding" if m >= 65 else \
            "contracting" if m <= 40 else "neutral"

    rel = legs.get("rel_1m") or {}
    breadth = legs.get("breadth") or {}
    rel_pos = sum(1 for v in rel.values()
                  if isinstance(v, (int, float)) and v > 0)
    b50 = breadth.get("pct_above_50")
    transmission = (
        "strong" if rel_pos >= 2 and isinstance(b50, (int, float))
        and b50 >= 60 else
        "weak" if rel_pos == 0 and isinstance(b50, (int, float))
        and b50 < 40 else "moderate")
    direction = ("improving" if score is not None and score >= 65 else
                 "deteriorating" if score is not None and score <= 44
                 else "neutral")

    # M2 — context only, never scored: broad money supply is not money
    # allocated to equities (the spec's own warning). Displayed so the
    # old M2-module read stays visible beside the real decomposition.
    context = {}
    try:
        m2 = _fred_series("M2SL", days=400)
        m2_yoy = _pct_chg(m2, 12)            # monthly series
        if m2_yoy is not None:
            context["m2_yoy"] = round(m2_yoy * 100, 1)
            context["m2_obs"] = str(m2[-1][0])
    except Exception:
        pass

    recovery = _recovery_sequence(comps, flow, legs.get("breadth")
                                  or {})

    # separate scores per the spec — combined only in the headline,
    # never averaged away: a strong composite can hide a failing leg
    def _sub(*names: str) -> Optional[int]:
        sc = [c for c in comps if c["name"] in names
              and c.get("score") is not None]
        return round(sum(c["score"] * c["weight"] for c in sc)
                     / sum(c["weight"] for c in sc)) \
            if sc and sum(c["weight"] for c in sc) else \
            (round(sum(c["score"] for c in sc) / len(sc)) if sc
             else None)

    hy_sc = next((c["score"] for c in comps
                  if c["name"] == "credit_conditions"), None)
    cd = credit_x.get("credit_depth_score")
    sub_scores = {
        "liquidity": _sub("fed_balance_sheet", "tga", "reverse_repo",
                          "bank_reserves", "bank_credit"),
        "credit_stress": (round(0.6 * hy_sc + 0.4 * cd)
                         if hy_sc is not None and cd is not None
                         else _sub("credit_conditions",
                                   "financial_conditions")),
        "equity_flows": _sub("equity_flows_proxy"),
        "market_confirmation": _sub("market_breadth"),
        "recovery": recovery["recovery_score"],
    }

    return {"liquidity_score": score, "band": band,
            "sub_scores": sub_scores,
            "flow_matrix": flow,
            "credit_depth": credit_x,
            "recovery": recovery,
            "context": context,
            "coverage": coverage,
            "components": comps,
            "impulses": {
                "fed": impulse("fed_balance_sheet"),
                "treasury": impulse("tga"),
                "reverse_repo": impulse("reverse_repo"),
                "bank_credit": impulse("bank_reserves", "bank_credit"),
                "financial_conditions": impulse("credit_conditions",
                                               "financial_conditions"),
                "equity_flows": impulse("equity_flows_proxy")},
            "liquidity_direction": direction,
            "equity_transmission": transmission,
            "flow_character": flow_char,
            "obs_dates": obs_dates,
            # fetch-age ≠ data-age: snapshot may be 0d old while the
            # underlying prints are days apart (weekly H.4.1 cadence)
            "data_window": {
                "newest": max(obs_dates.values()) if obs_dates else None,
                "oldest": min(obs_dates.values()) if obs_dates else None,
                "oldest_age_days": max(
                    (c.get("obs_age") or 0 for c in comps), default=0),
            },
            "breadth": legs.get("breadth") or {}}


def _prior_score(days: int = 30) -> Optional[int]:
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT score FROM liquidity_snapshots"
            " WHERE as_of <= CURRENT_DATE - :d"
            " ORDER BY as_of DESC LIMIT 1", {"d": days})
        return r[0]["score"] if r else None
    except Exception:
        return None


def run() -> dict[str, Any]:
    """Compute + journal a liquidity_snapshots row. Daily post-close
    — market legs move daily; weekly FRED prints just repeat (obs_age
    discloses staleness)."""
    from app.database import db
    st = evaluate()
    prev = _prior_score()
    prev7 = _prior_score(7)
    st["liquidity_acceleration"] = (
        "accelerating" if prev is not None and st["liquidity_score"]
        is not None and st["liquidity_score"] - prev >= 5 else
        "decelerating" if prev is not None and st["liquidity_score"]
        is not None and st["liquidity_score"] - prev <= -5 else
        "stable")
    # numeric delta — the reviewer's acceleration score; a poor-but-
    # improving read is the early-recovery signal a label can't show
    st["score_delta_7d"] = (
        st["liquidity_score"] - prev7
        if prev7 is not None and st["liquidity_score"] is not None
        else None)
    try:
        db.execute_update(
            "INSERT INTO liquidity_snapshots (as_of, score, band,"
            " direction, acceleration, transmission, components,"
            " impulses, payload) VALUES (:d,:s,:b,:di,:a,:t,"
            " CAST(:c AS jsonb),CAST(:i AS jsonb),CAST(:p AS jsonb))"
            " ON CONFLICT (as_of) DO UPDATE SET"
            " score=EXCLUDED.score, band=EXCLUDED.band,"
            " direction=EXCLUDED.direction,"
            " acceleration=EXCLUDED.acceleration,"
            " transmission=EXCLUDED.transmission,"
            " components=EXCLUDED.components,"
            " impulses=EXCLUDED.impulses, payload=EXCLUDED.payload",
            {"d": date.today(), "s": st["liquidity_score"],
             "b": st["band"], "di": st["liquidity_direction"],
             "a": st["liquidity_acceleration"],
             "t": st["equity_transmission"],
             "c": json.dumps(st["components"]),
             "i": json.dumps(st["impulses"]),
             "p": json.dumps(st, default=str)})
    except Exception as exc:
        logger.warning("liquidity journal: %s", exc)
        st["journal_error"] = str(exc)[:120]
    return st


def read() -> Optional[dict[str, Any]]:
    """Latest journaled state — the regime card's fast read."""
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT as_of, payload FROM liquidity_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
        if not rows:
            return None
        p = rows[0].get("payload")
        if isinstance(p, str):
            p = json.loads(p)
        p = p or {}
        d = rows[0]["as_of"]
        p["as_of"] = str(d)
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        p["age_days"] = (date.today() - d).days
        return p
    except Exception:
        return None
