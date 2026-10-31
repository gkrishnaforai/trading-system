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


def _equity_score(legs: dict) -> tuple[Optional[int], Optional[int]]:
    """(fund-flows-proxy score, breadth score) — each 0-100 or None."""
    rel = (legs.get("rel_1m") or {})
    breadth = legs.get("breadth") or {}
    bs = breadth.get("breadth_score")
    bs_score = int(max(0, min(100, round(bs)))) \
        if isinstance(bs, (int, float)) else None
    # relative-strength → score: +3% vs SPY = leadership = 85
    vals = [v for v in rel.values() if isinstance(v, (int, float))]
    flow = None
    if vals:
        m = sum(vals) / len(vals)
        flow = 90 if m >= 0.03 else 75 if m >= 0.01 else \
            60 if m >= 0 else 40 if m >= -0.01 else \
            25 if m >= -0.03 else 10
    return flow, bs_score


def evaluate() -> dict[str, Any]:
    """Compute the state — no journal (run() wraps it)."""
    comps = []
    obs_dates: dict[str, str] = {}
    for name, w, sid, back, inv in _COMPONENTS:
        pts = _fred_series(sid, days=220)
        chg = _pct_chg(pts, back)
        if pts:
            obs_dates[sid] = str(pts[-1][0])
        comps.append({"name": name, "weight": w, "series": sid,
                      "chg_pct": round(chg, 4) if chg is not None
                      else None,
                      "score": _band(chg, inv)})
    nfci = _nfci()
    comps.append({"name": "financial_conditions", "weight": 0,
                  "series": "NFCI", "score": nfci,
                  "note": "level, part of credit leg"})
    legs = _equity_legs()
    flow_sc, breadth_sc = _equity_score(legs)
    comps.append({"name": "equity_flows_proxy", "weight": 15,
                  "series": "SMH/QQQ/IWM vs SPY",
                  "score": flow_sc,
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
    return {"liquidity_score": score, "band": band,
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
            "obs_dates": obs_dates,
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
    """Compute + journal a liquidity_snapshots row. Weekly cadence —
    the heavy series (WALCL/WRESBAL/WTREGEN) print weekly."""
    from app.database import db
    st = evaluate()
    prev = _prior_score()
    st["liquidity_acceleration"] = (
        "accelerating" if prev is not None and st["liquidity_score"]
        is not None and st["liquidity_score"] - prev >= 5 else
        "decelerating" if prev is not None and st["liquidity_score"]
        is not None and st["liquidity_score"] - prev <= -5 else
        "stable")
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
