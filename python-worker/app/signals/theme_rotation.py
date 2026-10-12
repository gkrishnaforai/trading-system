"""Theme-rotation environment score — is the AI/infra cohort itself
de-risking relative to the broad market? The regime engine answers
"is the market bearish"; this answers "is THE TRADE unwinding" —
Oct-7-2026 regime read NEUTRAL while the AI cohort was already
rotating. Directional bear-alpha entries are permissioned by this,
not by SPY.

Legs (all from daily_bars + latest regime VIX — no new providers):

  25  AI basket vs SPY relative strength (20d)
  20  semis (SMH) vs SPY (20d)
  15  AI breadth — share of theme names below their 20d SMA
  15  defensive rotation — XLE + XLP vs SPY (10d)
  10  rate shock — ^TNX 5d change (yield index, pts)
  10  oil shock — USO 5d change
   5  VIX level (latest regime snapshot)

Bands: <30 low · 30-45 watch · 45-60 candidates emerging ·
60-75 bear-alpha environment · >75 strong defensive.

Directional-put consumers only — the hedge book buys insurance when
it's cheap (calm tape), so this gates put_entry, never put_universe
tiers.
"""
from __future__ import annotations

import logging
from datetime import date
from statistics import mean
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BANDS = ((75, "strong_defensive"), (60, "bear_alpha"),
          (45, "candidates_emerging"), (30, "watch"), (0, "low"))


def _closes(sym: str, n: int = 60,
            as_of: Optional[date] = None) -> list[float]:
    """Most recent `n` closes, newest first, optionally point-in-time."""
    from app.database import db
    d = as_of or date.today()
    try:
        return [float(r["close"]) for r in db.execute_query(
            "SELECT close FROM daily_bars WHERE symbol=:s "
            "AND date<=:d ORDER BY date DESC LIMIT :n",
            {"s": sym, "d": d, "n": n})]
    except Exception:
        return []


def _ret(c: list[float], n: int) -> Optional[float]:
    return c[0] / c[n] - 1 if len(c) > n and c[n] else None


def _rs(c: list[float], bench: list[float], n: int) -> Optional[float]:
    a, b = _ret(c, n), _ret(bench, n)
    return a - b if a is not None and b is not None else None


def compute(as_of: Optional[date] = None) -> dict[str, Any]:
    """Score the AI-rotation environment. `as_of` enables replays."""
    from app.options.put_universe import _THEME_BETA  # theme list lives
    # there — single source for 'what counts as the AI-infra book'

    legs: dict[str, Any] = {}
    spy = _closes("SPY", 30, as_of)
    missing = []

    # ---- 25 · AI basket vs SPY (equal-weight, fast+slow) -----------
    basket: list[list[float]] = []
    below20 = 0
    counted = 0
    for s in _THEME_BETA:
        c = _closes(s, 25, as_of)
        if len(c) < 21:
            continue
        basket.append(c)
        counted += 1
        if c[0] < mean(c[:20]):
            below20 += 1
    spr20, spr5 = _ret(spy, 20), _ret(spy, 5)
    r20 = [_ret(c, 20) for c in basket]
    r5 = [_ret(c, 5) for c in basket]
    if spr20 is not None and spr5 is not None and r20 and r5:
        s20 = mean(x for x in r20 if x is not None) - spr20
        s5 = mean(x for x in r5 if x is not None) - spr5
        legs["ai_vs_spy"] = {
            "spread_5d": round(s5, 3), "spread_20d": round(s20, 3),
            "pts": max(
                25 if s20 <= -0.06 else 21 if s20 <= -0.04 else
                15 if s20 <= -0.02 else 9 if s20 <= 0 else
                3 if s20 <= 0.03 else 0,
                25 if s5 <= -0.03 else 21 if s5 <= -0.02 else
                15 if s5 <= -0.01 else 9 if s5 <= 0 else 0)}
    else:
        missing.append("ai_vs_spy")

    # ---- 20 · semis vs SPY (fast+slow) ------------------------------
    smh = _closes("SMH", 25, as_of)
    v20, v5 = _rs(smh, spy, 20), _rs(smh, spy, 5)
    if v20 is not None or v5 is not None:
        p20 = (20 if v20 <= -0.05 else 16 if v20 <= -0.03 else
               12 if v20 <= -0.01 else 6 if v20 <= 0.01 else 0) \
            if v20 is not None else 0
        p5 = (20 if v5 <= -0.025 else 16 if v5 <= -0.015 else
              12 if v5 <= -0.005 else 6 if v5 <= 0.005 else 0) \
            if v5 is not None else 0
        legs["semis_vs_spy"] = {
            "spread_5d": round(v5, 3) if v5 is not None else None,
            "spread_20d": round(v20, 3) if v20 is not None else None,
            "pts": max(p20, p5)}
    else:
        missing.append("semis_vs_spy")

    # ---- 15 · AI breadth -------------------------------------------
    if counted:
        frac = below20 / counted
        legs["breadth"] = {"below20_pct": round(frac, 2), "pts": (
            15 if frac >= 0.70 else 12 if frac >= 0.55 else
            8 if frac >= 0.40 else 4 if frac >= 0.25 else 0)}
    else:
        missing.append("breadth")

    # ---- 15 · defensive rotation (XLE + XLP vs SPY, 10d) -----------
    dpts = 0.0
    for etf in ("XLE", "XLP"):
        v = _rs(_closes(etf, 15, as_of), spy, 10)
        if v is not None:
            dpts += 7.5 if v > 0.03 else 5 if v > 0.01 else 0
        else:
            missing.append(f"{etf.lower()}_rs")
    legs["defensive_rotation"] = {"pts": min(15.0, dpts)}

    # ---- 10 · rate shock (^TNX 5d — index pts, 1pt ≈ 10bp) ---------
    tnx = _closes("^TNX", 8, as_of)
    if len(tnx) > 5:
        dv = tnx[0] - tnx[5]
        legs["rate_shock"] = {"tnx_5d": round(dv, 2), "pts": (
            10 if dv >= 2.0 else 6 if dv >= 1.0 else
            3 if dv >= 0.5 else 0)}
    else:
        missing.append("rate_shock")

    # ---- 10 · oil shock (USO 5d) -----------------------------------
    uso = _closes("USO", 8, as_of)
    v = _ret(uso, 5)
    if v is not None:
        legs["oil_shock"] = {"uso_5d": round(v, 3), "pts": (
            10 if v >= 0.08 else 5 if v >= 0.04 else 0)}
    else:
        missing.append("oil_shock")

    # ---- 5 · VIX ---------------------------------------------------
    try:
        from app.database import db
        r = db.execute_query(
            "SELECT vix FROM regime_snapshots WHERE as_of<=:d "
            "ORDER BY as_of DESC LIMIT 1", {"d": as_of or date.today()})
        vix = float(r[0]["vix"]) if r and r[0].get("vix") else None
    except Exception:
        vix = None
    if vix is not None:
        legs["vix"] = {"vix": vix, "pts": (
            5 if vix >= 30 else 3.5 if vix >= 22 else 2 if vix >= 18
            else 0)}
    else:
        missing.append("vix")

    score = round(sum(l["pts"] for l in legs.values()), 1)
    band = next(b for cut, b in _BANDS if score >= cut)
    return {"as_of": str(as_of or date.today()), "score": score,
            "band": band, "legs": legs, "missing": missing,
            "data_partial": bool(missing)}


def _persist(row: dict) -> None:
    from app.database import db
    import json
    try:
        db.execute_update(
            "INSERT INTO theme_rotation_snapshots "
            "(as_of, score, band, legs, missing) "
            "VALUES (:d,:s,:b,CAST(:l AS jsonb),CAST(:m AS jsonb)) "
            "ON CONFLICT (as_of) DO UPDATE SET score=EXCLUDED.score,"
            " band=EXCLUDED.band, legs=EXCLUDED.legs,"
            " missing=EXCLUDED.missing",
            {"d": row["as_of"], "s": row["score"], "b": row["band"],
             "l": json.dumps(row["legs"]),
             "m": json.dumps(row["missing"])})
    except Exception as exc:
        logger.debug("theme_rotation persist: %s", exc)


def current() -> dict[str, Any]:
    """Today's snapshot — recompute if absent (lazy daily cadence;
    piggybacks the callers' job schedules)."""
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT score, band, legs, missing "
            "FROM theme_rotation_snapshots WHERE as_of=:d",
            {"d": date.today()})
        if r:
            return {"as_of": str(date.today()),
                    "score": float(r[0]["score"]),
                    "band": r[0]["band"], "legs": r[0]["legs"],
                    "missing": r[0]["missing"],
                    "data_partial": bool(r[0]["missing"])}
    except Exception:
        pass
    row = compute()
    _persist(row)
    return row


def compute_for(as_of: date) -> dict[str, Any]:
    """Point-in-time score for replays — reads persisted row when the
    date has one, else recomputes off bars (deterministic either way)."""
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT score, band, legs, missing "
            "FROM theme_rotation_snapshots WHERE as_of=:d",
            {"d": as_of})
        if r:
            return {"as_of": str(as_of), "score": float(r[0]["score"]),
                    "band": r[0]["band"], "legs": r[0]["legs"],
                    "missing": r[0]["missing"],
                    "data_partial": bool(r[0]["missing"])}
    except Exception:
        pass
    return compute(as_of)
