"""Short-squeeze / short-covering signal — deterministic, evidence-
bounded, and deliberately SEPARATE from fundamental and tape scores.

Two outputs per symbol:

  squeeze_fuel (0-100)      — how crowded the short trade is
                              (SI% + days-to-cover). Answer to
                              "could this squeeze?", not "is it?".
  covering_probability      — for a rally currently underway, the
                              probability it is driven by shorts buying
                              to close rather than new accumulation.

What we can and cannot claim (FINRA contract):
- short_interest is a biweekly POSITION snapshot, up to ~2w stale —
  fuel, not proof.
- short_volume is daily FLOW of short-sale orders. Covering buys are
  NOT marked short, so a FALLING ratio while price rises is the
  covering signature; a RISING ratio means shorts are pressing into
  strength — a different, adversarial signal.
- No borrow-fee or locate feed exists here. A high score means
  "consistent with covering", never "proven covering".

Verdicts:
  likely_covering      rally + fuel + covering signatures → fade risk
                       once covering exhausts; do NOT treat as
                       accumulation or durable stabilization
  new_shorts_pressing  rally but short-sale ratio RISING → shorts are
                       adding; crowded both ways, volatile
  genuine_accumulation rally without squeeze signature → consistent
                       with real buying
  squeeze_setup        no rally yet, but high fuel + tape stabilizing
                       → a real bid could trigger a covering rally
  no_clear_signal      rally exists but evidence is mixed/thin
  insufficient_data    missing SI AND SV → we do not guess
"""
from __future__ import annotations

import json
from datetime import date
from statistics import mean
from typing import Any, Optional

from app.observability.logging import get_logger

logger = get_logger("short_squeeze")


def _f(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


# ------------------------------ inputs ---------------------------------

def _load_inputs(symbol: str) -> dict[str, Any]:
    from app.database import db
    si = db.execute_query(
        "SELECT short_interest_date AS d, short_interest AS si,"
        " short_percent AS pct, days_to_cover AS dtc"
        " FROM short_interest WHERE symbol=:s"
        " ORDER BY short_interest_date DESC LIMIT 2",
        {"s": symbol})
    sv = db.execute_query(
        "SELECT short_volume_date AS d, short_volume_percent AS ratio"
        " FROM short_volume WHERE symbol=:s"
        " ORDER BY short_volume_date DESC LIMIT 12",
        {"s": symbol})
    bars = db.execute_query(
        "SELECT date, open, high, low, close, volume FROM daily_bars"
        " WHERE symbol=:s ORDER BY date DESC LIMIT 40",
        {"s": symbol})
    fw = db.execute_query(
        "SELECT est_revision_pct, beat_streak, last_surprise_pct"
        " FROM symbol_flywheel WHERE symbol=:s", {"s": symbol})
    st = db.execute_query(
        "SELECT momentum_state, next_earnings_date FROM stocks"
        " WHERE symbol=:s", {"s": symbol})
    return {"si": si, "sv": sv, "bars": bars,
            "fw": fw[0] if fw else {},
            "stock": st[0] if st else {}}


# ------------------------------ fuel -----------------------------------

def _fuel(si_pct: Optional[float], dtc: Optional[float]) -> float:
    leg = 0.0
    if si_pct is not None:
        leg += min(60.0, max(0.0, (si_pct - 3.0) * 60.0 / 22.0))
    if dtc is not None:
        leg += min(40.0, max(0.0, (dtc - 1.0) * 40.0 / 6.0))
    return round(min(100.0, leg), 1)


# ------------------------------ evaluate -------------------------------

def evaluate(symbol: str, persist: bool = False) -> dict[str, Any]:
    d = _load_inputs(symbol)
    bars, si, sv = d["bars"], d["si"], d["sv"]
    ev: list[str] = []

    def _ret(out: dict) -> dict:
        if persist:
            _persist(out)
        return out

    if not bars:
        return _ret({"symbol": symbol, "verdict": "insufficient_data",
                     "fuel": None, "covering_probability": None,
                     "data_quality": "missing", "rally": None,
                     "evidence": ["no daily bars"]})

    close = [float(b["close"]) for b in bars]
    px = close[0]

    # rally detection — ret over 1d / 5d, rel volume vs 20d avg,
    # distance off the 20d low
    ret_1d = (close[0] / close[1] - 1) if len(close) > 1 else 0.0
    ret_5d = (close[0] / close[5] - 1) if len(close) > 5 else 0.0
    vols = [float(b["volume"] or 0) for b in bars[1:21]]
    rel_vol = (float(bars[0]["volume"] or 0) / mean(vols)
               if vols and mean(vols) > 0 else None)
    low20 = min(float(b["low"]) for b in bars[:20])
    off_low = px / low20 - 1 if low20 else None
    rally = ret_5d > 0.07 or ret_1d > 0.05 or \
        (rel_vol is not None and rel_vol >= 2 and ret_1d > 0.02)

    # fuel — from latest SI snapshot (position, biweekly-stale)
    si_now = si[0] if si else {}
    si_pct = _f(si_now.get("pct"))
    dtc = _f(si_now.get("dtc"))
    fuel = _fuel(si_pct, dtc)
    if si:
        age = (date.today() - si_now["d"]).days if si_now.get("d") else None
        ev.append(f"SI {si_pct or '?'}% of shares out · "
                  f"{dtc or '?'}d to cover (snapshot {si_now.get('d')}"
                  f"{f', {age}d old' if age else ''})")

    # short-volume ratio trend — covering signature needs the rally
    # window: compare last-3-session mean ratio vs the prior 5
    sv_trend = None
    ratios = [_f(r["ratio"]) for r in sv]
    ratios = [r for r in ratios if r is not None]
    if len(ratios) >= 6:
        recent, prior = ratios[:3], ratios[3:8]
        sv_trend = round(mean(recent) - mean(prior), 2)
        ev.append(f"short-sale ratio {mean(recent):.0f}% last 3d "
                  f"vs {mean(prior):.0f}% prior "
                  f"({'falling' if sv_trend < -1 else 'rising' if sv_trend > 1 else 'flat'})")

    # SI delta across snapshots (confirmed, but backward-looking)
    si_delta = None
    if len(si) == 2 and si[1].get("si"):
        si_delta = _f(si[0]["si"]) / _f(si[1]["si"]) - 1 \
            if _f(si[1]["si"]) else None
        if si_delta is not None:
            ev.append(f"SI {si_delta * 100:+.0f}% between "
                      f"{si[1]['d']} → {si[0]['d']} settlements")

    # catalyst — does a fundamental improvement explain the rally?
    fw = d["fw"]
    rev = _f(fw.get("est_revision_pct"))
    surprise = _f(fw.get("last_surprise_pct"))
    catalyst_absent = (rev is not None and rev <= 0) and \
        (surprise is None or surprise <= 5)
    if rev is not None:
        ev.append(f"est revisions {rev:+.0f}%"
                  + (" — rally not explained by estimates"
                     if catalyst_absent else " — estimates improving"))

    # exhaustion signature — latest close in lower half of day range
    b0 = bars[0]
    rng = float(b0["high"]) - float(b0["low"])
    fade = rng > 0 and (px - float(b0["low"])) / rng < 0.4
    if fade and rally:
        ev.append("latest close in lower 40% of range — rally fading")

    # ---------------- covering probability ----------------
    missing_si, missing_sv = not si, len(ratios) < 4
    if missing_si and missing_sv:
        return _ret({"symbol": symbol, "verdict": "insufficient_data",
                     "fuel": fuel if si else None,
                     "covering_probability": None,
                     "data_quality": "missing", "rally": rally,
                     "ret_5d": round(ret_5d, 4),
                     "si_pct": si_pct, "days_to_cover": dtc,
                     "evidence": ev or
                     ["no short-interest or short-volume data"]})

    if not rally:
        # no upside momentum to attribute — but fuel may still be a
        # setup if the tape is stabilizing
        mom = d["stock"].get("momentum_state") or ""
        setup = fuel >= 50 and mom in ("basing", "stabilizing",
                                       "recovery", "pullback")
        return _ret({"symbol": symbol,
                     "verdict": "squeeze_setup" if setup
                     else "no_clear_signal",
                     "fuel": fuel, "covering_probability": None,
                     "data_quality": "partial" if missing_si or missing_sv
                     else "full",
                     "rally": False, "ret_5d": round(ret_5d, 4),
                     "si_pct": si_pct, "days_to_cover": dtc,
                     "sv_ratio_latest": ratios[0] if ratios else None,
                     "sv_trend": sv_trend,
                     "evidence": ev})

    prob = 0.0
    if sv_trend is not None:
        if sv_trend <= -3:
            prob += 35
        elif sv_trend <= -1:
            prob += 20
        elif sv_trend >= 2:
            prob -= 25
    if si_delta is not None and si_delta <= -0.05:
        prob += 25
    if rel_vol is not None and rel_vol >= 2:
        prob += 15
    if catalyst_absent:
        prob += 15
    elif rev is not None and rev > 5:
        prob -= 15
    if fade:
        prob += 10

    prob *= min(1.0, fuel / 50.0)      # no fuel → no squeeze
    prob = max(0.0, min(100.0, prob))
    if missing_si or missing_sv:
        prob = min(prob, 45.0)         # partial evidence → bounded

    pressing = sv_trend is not None and sv_trend >= 2 and fuel >= 30
    if prob >= 60:
        verdict = "likely_covering"
    elif pressing:
        verdict = "new_shorts_pressing"
    elif fuel < 20 and not catalyst_absent:
        verdict = "genuine_accumulation"
    else:
        verdict = "no_clear_signal"

    out = {"symbol": symbol, "verdict": verdict,
           "fuel": fuel,
           "covering_probability": round(prob, 1),
           "data_quality": "partial" if missing_si or missing_sv
           else "full",
           "rally": True, "ret_5d": round(ret_5d, 4),
           "ret_1d": round(ret_1d, 4), "rel_vol":
           round(rel_vol, 2) if rel_vol else None,
           "off_low20": round(off_low, 4) if off_low else None,
           "si_pct": si_pct, "days_to_cover": dtc,
           "si_delta": round(si_delta, 4) if si_delta else None,
           "sv_ratio_latest": ratios[0] if ratios else None,
           "sv_trend": sv_trend, "evidence": ev}
    return _ret(out)


def _persist(o: dict[str, Any]) -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO short_squeeze_evals"
        " (symbol, as_of, fuel, covering_probability, verdict,"
        "  data_quality, rally, ret_5d, rel_vol, si_pct,"
        "  days_to_cover, sv_ratio_latest, sv_trend, evidence)"
        " VALUES (:symbol, CURRENT_DATE, :fuel, :prob, :verdict,"
        "  :dq, :rally, :ret5, :rv, :si, :dtc, :svr, :svt,"
        "  CAST(:ev AS jsonb))"
        " ON CONFLICT (symbol, as_of) DO UPDATE SET"
        " fuel=EXCLUDED.fuel,"
        " covering_probability=EXCLUDED.covering_probability,"
        " verdict=EXCLUDED.verdict,"
        " data_quality=EXCLUDED.data_quality,"
        " rally=EXCLUDED.rally, ret_5d=EXCLUDED.ret_5d,"
        " rel_vol=EXCLUDED.rel_vol, si_pct=EXCLUDED.si_pct,"
        " days_to_cover=EXCLUDED.days_to_cover,"
        " sv_ratio_latest=EXCLUDED.sv_ratio_latest,"
        " sv_trend=EXCLUDED.sv_trend,"
        " evidence=EXCLUDED.evidence",
        {"symbol": o["symbol"], "fuel": o.get("fuel"),
         "prob": o.get("covering_probability"),
         "verdict": o["verdict"], "dq": o.get("data_quality"),
         "rally": o.get("rally"), "ret5": o.get("ret_5d"),
         "rv": o.get("rel_vol"), "si": o.get("si_pct"),
         "dtc": o.get("days_to_cover"),
         "svr": o.get("sv_ratio_latest"), "svt": o.get("sv_trend"),
         "ev": json.dumps(o.get("evidence") or [])})


# ------------------------------ scan -----------------------------------

def scan(symbols: Optional[list[str]] = None,
         persist: bool = True) -> dict[str, Any]:
    """Evaluate every tracked symbol that has ANY short data — a name
    with no SI and no SV is 'insufficient_data', not 'clean'."""
    from app.database import db
    if symbols is None:
        rows = db.execute_query(
            "SELECT DISTINCT symbol FROM ("
            "  SELECT symbol FROM short_interest"
            "  UNION SELECT symbol FROM short_volume) t")
        symbols = [r["symbol"] for r in rows]
    evals = []
    for s in symbols:
        try:
            e = evaluate(s, persist=persist)
            if e.get("verdict") != "insufficient_data":
                evals.append(e)
        except Exception as ex:                          # noqa: BLE001
            logger.warning("squeeze eval %s: %s", s, ex)
    rank = {"likely_covering": 0, "new_shorts_pressing": 1,
            "squeeze_setup": 2, "no_clear_signal": 3,
            "genuine_accumulation": 4}
    evals.sort(key=lambda e: (rank.get(e["verdict"], 5),
                              -(e.get("fuel") or 0)))
    return {"as_of": str(date.today()), "count": len(evals),
            "evals": evals}


def flags(symbols: list[str]) -> dict[str, dict]:
    """Lightweight map for other engines: latest persisted verdict per
    symbol (falls back to live eval if today's row is missing)."""
    from app.database import db
    if not symbols:
        return {}
    rows = db.execute_query(
        "SELECT DISTINCT ON (symbol) symbol, verdict, fuel,"
        " covering_probability, sv_trend, data_quality"
        " FROM short_squeeze_evals WHERE symbol = ANY(:s)"
        " ORDER BY symbol, as_of DESC", {"s": symbols})
    out = {}
    for r in rows:
        out[r["symbol"]] = {
            "verdict": r["verdict"], "fuel": _f(r["fuel"]),
            "covering_probability": _f(r["covering_probability"]),
            "sv_trend": _f(r["sv_trend"]),
            "data_quality": r["data_quality"]}
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(json.dumps(evaluate(sys.argv[1]), indent=2, default=str))
    else:
        print(json.dumps(scan(persist=False), indent=2, default=str))
