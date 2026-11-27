"""Session-to-session forecast — yesterday's tape → today's direction.

The desk already journals the day arc: premarket_snapshots (overnight
gaps), intraday_evals (15-min tape reads + heuristic forecast, graded
against the close), daily_bars (outcomes). This module ties the arc
into a cross-session forecast with three journaled stages, one row
each per target session — never overwritten:

  baseline   after close of session T  — T's tape quality, breadth,
             leadership and recovery structure → prior for T+1
  premarket  before open of session T+1 — overnight futures, gaps,
             yields/vol moves update the prior before the tape speaks
  outcome    next day's actual return graded back onto both rows —
             the score earns calibration, never declares it

Missing data stays None, not zero. The score is a heuristic prior
(basis disclosed in forecast.basis) — it becomes a probability only
once the outcome column accrues enough history to calibrate against.
Restricted surface: admin-only, behind the market_forecast flag.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dtime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.observability.logging import get_logger

logger = get_logger("session_forecast")

_ET = ZoneInfo("America/New_York")


# --------------------------- session calendar --------------------------

def _is_trading_day(d: date) -> bool:
    from app.utils.trading_calendar import expected_trading_days
    return d in expected_trading_days(d, d)


def _next_trading_day(d: date) -> Optional[date]:
    from datetime import timedelta
    from app.utils.trading_calendar import expected_trading_days
    days = expected_trading_days(d + timedelta(days=1),
                                 d + timedelta(days=10))
    return days[0] if days else None


def _session_type(d: date, n_bars: int) -> str:
    """full / early_close / unknown — expected 5m-bar count for the
    session says whether the tape deserves full predictive weight
    (a 3.5h holiday session journals its type; consumers decide the
    reliability discount)."""
    try:
        from app.utils.trading_calendar import (
            expected_intraday_5m_timestamps)
        expected = len(expected_intraday_5m_timestamps(d, d))
        if expected < 78:
            return "early_close"
    except Exception:
        pass
    return "full" if n_bars >= 70 else ("early_close"
                                        if n_bars >= 25 else "unknown")


# --------------------------- tape extraction ---------------------------

def _tape(raw: dict[str, list[dict]], breadth: dict) -> dict[str, Any]:
    """Session-tape features for the baseline — the observed-evidence
    half of the forecast. Everything computable is stored; what the
    feed can't give (market-wide adv/dec) stays None, honestly."""
    from app.signals import intraday_pulse as ip
    qqq = ip._day_stats(raw.get("QQQ") or [])
    spy = ip._day_stats(raw.get("SPY") or [])
    smh = ip._day_stats(raw.get("SMH") or [])
    iwm = ip._day_stats(raw.get("IWM") or [])
    vix = ip._day_stats(raw.get("^VIX") or [])
    tnx = ip._day_stats(raw.get("^TNX") or [])
    if not qqq:
        return {}

    def ret(d: dict) -> Optional[float]:
        c = d.get("chg_open")
        return round(c * 100, 2) if c is not None else None

    vix_trend = ip._trend(raw.get("^VIX") or [])
    smh_rs = (smh.get("chg_open") - qqq.get("chg_open")
              if smh.get("chg_open") is not None
              and qqq.get("chg_open") is not None else None)
    return {
        "close_location_value": qqq.get("close_location"),
        "vwap_control_pct": qqq.get("vwap_above_pct"),
        "vwap_reclaim_bar": qqq.get("vwap_reclaim_bar"),
        "vwap_crosses": qqq.get("vwap_crosses"),
        "first_30m_return": (round(qqq["first_30m_ret"] * 100, 2)
                             if qqq.get("first_30m_ret") is not None
                             else None),
        "low_to_close_return": (round(qqq["low_to_close"] * 100, 2)
                                if qqq.get("low_to_close") is not None
                                else None),
        "intraday_drawdown": (round(qqq["drawdown"] * 100, 2)
                              if qqq.get("drawdown") is not None
                              else None),
        "up_down_volume_ratio": qqq.get("up_down_vol"),
        "book_adv_pct": breadth.get("adv_pct"),
        "book_n": breadth.get("n"),
        "spy_ret": ret(spy), "qqq_ret": ret(qqq),
        "smh_ret": ret(smh), "iwm_ret": ret(iwm),
        "smh_vs_qqq": round(smh_rs * 100, 2) if smh_rs is not None else None,
        "vix_chg": ret(vix),
        "vix_trend": round(vix_trend * 100, 2) if vix_trend else None,
        "tnx_chg": ret(tnx),
        "n_bars": qqq.get("n_bars"),
    }


def _rqs(t: dict) -> Optional[float]:
    """Recovery Quality Score 0-100 — was the source session's rally
    a genuine broad recovery or a low-liquidity bounce? Components
    score 0-1 then weight; a missing leg is dropped and the total
    renormalised (coverage disclosed alongside)."""
    def lerp(x: Optional[float], lo: float, hi: float) -> Optional[float]:
        if x is None:
            return None
        return max(0.0, min(1.0, (x - lo) / (hi - lo)))

    adv = t.get("book_adv_pct")
    parts = [
        (lerp(t.get("vwap_control_pct"), 30, 80), 20),     # VWAP control
        (t.get("close_location_value"), 15),               # close location
        (lerp(adv, 35, 70), 20),                           # breadth
        (lerp(t.get("smh_vs_qqq"), -1.0, 1.5), 15),        # semis leadership
        (lerp(t.get("up_down_volume_ratio"), 0.7, 1.6), 10),
        ((1.0 if (t.get("vix_chg") or 0) < 0 else 0.0)
         if t.get("vix_chg") is not None else None, 10),   # VIX improving
        (lerp(t.get("low_to_close_return"), 0.0, 2.0), 10),# higher-low close
    ]
    scored = [(v, w) for v, w in parts if v is not None]
    if not scored:
        return None
    tot_w = sum(w for _, w in scored)
    return round(sum(v * w for v, w in scored) / tot_w * 100, 1)


# --------------------------- scoring -----------------------------------

def _direction(components: dict[str, Optional[float]]) -> dict[str, Any]:
    """Monday-Direction-Score shape — each component is 0-100 and the
    total renormalises over legs that have data. Baseline only has
    tape/breadth/leadership/background; premarket adds the overnight
    legs; coverage is disclosed, not hidden."""
    weights = {"tape": 20, "breadth": 15, "leadership": 10,
               "overnight": 15, "rates_vol": 15,
               "open_confirm": 10, "rth_confirm": 10, "credit": 5}
    scored = {k: v for k, v in components.items()
              if v is not None and k in weights}
    tot_w = sum(weights[k] for k in scored)
    score = (round(sum(scored[k] * weights[k] for k in scored)
                   / tot_w, 1) if tot_w else None)
    band = (None if score is None else
            "strong_bullish" if score >= 80 else
            "bullish_bias" if score >= 65 else
            "mixed" if score >= 45 else
            "bearish_bias" if score >= 30 else "strong_bearish")
    return {"direction_score": score, "band": band,
            "coverage_pct": round(tot_w / 100 * 100),
            "components": {k: round(v, 1) for k, v in scored.items()},
            "basis": "heuristic_v1"}


def _clampf(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# --------------------------- stages ------------------------------------

def baseline() -> dict[str, Any]:
    """After the close: extract today's tape, score it, and journal the
    prior for the next trading session. Runs the same fetch as the
    intraday classifier — after-hours bars don't shift session stats."""
    from app.database import db
    from app.signals import intraday_pulse as ip
    today = datetime.now(_ET).date()
    if not _is_trading_day(today):
        return {"skipped": "not a trading day"}
    tgt = _next_trading_day(today)
    if not tgt:
        return {"skipped": "no next trading day found"}

    raw = ip._fetch_all()
    tape = _tape(raw, ip._book_breadth())
    if not tape:
        return {"skipped": "no session bars"}
    st = _session_type(today, tape.get("n_bars") or 0)
    rqs = _rqs(tape)

    # background legs the baseline can legitimately score: the
    # source-day rates/vol behaviour (TNX move) is evidence about
    # tomorrow too — it doesn't reset at midnight.
    components: dict[str, Optional[float]] = {
        "tape": rqs,
        "breadth": _clampf(((tape.get("book_adv_pct") or 0) - 30)
                           / 40 * 100, 0, 100)
                   if tape.get("book_adv_pct") is not None else None,
        "leadership": _clampf(50 + (tape.get("smh_vs_qqq") or 0) * 40,
                              0, 100)
                      if tape.get("smh_vs_qqq") is not None else None,
        "rates_vol": _clampf(50 - (tape.get("tnx_chg") or 0) * 15
                             - (tape.get("vix_chg") or 0) * 3, 0, 100)
                     if (tape.get("tnx_chg") is not None
                         or tape.get("vix_chg") is not None) else None,
    }
    fc = _direction(components)
    # a shortened session's tape earns less weight — halve the tape
    # component's contribution by re-scoring with a reduced weight
    if st == "early_close" and fc["direction_score"] is not None:
        fc["session_reliability"] = "reduced"

    row = {"forecast_date": str(tgt), "baseline_session": str(today),
           "baseline_session_type": st, "stage": "baseline",
           "tape": tape, "overnight": None,
           "forecast": {**fc, "rqs": rqs}}
    db.execute_update(
        "INSERT INTO session_forecasts (forecast_date, baseline_session,"
        " baseline_session_type, stage, tape, overnight, forecast)"
        " VALUES (:fd,:bs,:bst,:st,CAST(:t AS jsonb),CAST(:o AS jsonb),"
        " CAST(:f AS jsonb))"
        " ON CONFLICT (forecast_date, stage) DO UPDATE SET"
        " tape=EXCLUDED.tape, forecast=EXCLUDED.forecast,"
        " baseline_session_type=EXCLUDED.baseline_session_type",
        {"fd": row["forecast_date"], "bs": row["baseline_session"],
         "bst": st, "st": "baseline", "t": json.dumps(tape, default=str),
         "o": None, "f": json.dumps(row["forecast"], default=str)})
    return {"forecast_date": str(tgt), "score": fc["direction_score"],
            "band": fc["band"], "rqs": rqs, "session_type": st}


def premarket() -> dict[str, Any]:
    """Before the open: overnight futures + journaled gap snapshots +
    yields/vol update today's baseline into the premarket stage."""
    from app.database import db
    from app.signals import intraday_pulse as ip
    today = datetime.now(_ET).date()
    if not _is_trading_day(today):
        return {"skipped": "not a trading day"}
    base = db.execute_query(
        "SELECT baseline_session, tape, forecast FROM session_forecasts"
        " WHERE forecast_date=:d AND stage='baseline'", {"d": today})
    tape = (base[0]["tape"] if base else {}) or {}
    if isinstance(tape, str):
        tape = json.loads(tape)
    prior = (base[0]["forecast"] if base else {}) or {}
    if isinstance(prior, str):
        prior = json.loads(prior)
    src_session = (str(base[0]["baseline_session"]) if base
                   and base[0].get("baseline_session") else None)

    overnight: dict[str, Any] = {}
    pm = ip.premarket()                     # ES=NQ futures + gap-vs-ATR
    for k in ("es_chg_pct", "nq_chg_pct", "gap_vs_atr"):
        if pm.get(k) is not None:
            overnight[k] = pm[k]
    # journaled premarket gaps — SMH leg + crypto risk-sentiment
    rows = db.execute_query(
        "SELECT slot, smh_gap, qqq_gap, btc_chg, eth_chg"
        " FROM premarket_snapshots WHERE date=:d"
        " ORDER BY ts DESC LIMIT 1", {"d": today})
    if rows:
        r = rows[0]
        for k in ("smh_gap", "qqq_gap", "btc_chg", "eth_chg"):
            if r.get(k) is not None:
                overnight[k] = float(r[k])

    es = overnight.get("es_chg_pct")
    nq = overnight.get("nq_chg_pct")
    components: dict[str, Optional[float]] = {
        **{k: (prior.get("components") or {}).get(k)
           for k in ("tape", "breadth", "leadership", "rates_vol")},
        "overnight": _clampf(50 + ((es or 0) + (nq or 0)) * 12, 0, 100)
                     if (es is not None or nq is not None) else None,
    }
    fc = _direction(components)
    db.execute_update(
        "INSERT INTO session_forecasts (forecast_date, baseline_session,"
        " baseline_session_type, stage, tape, overnight, forecast)"
        " VALUES (:fd,:bs,:bst,'premarket',CAST(:t AS jsonb),"
        " CAST(:o AS jsonb),CAST(:f AS jsonb))"
        " ON CONFLICT (forecast_date, stage) DO UPDATE SET"
        " overnight=EXCLUDED.overnight, forecast=EXCLUDED.forecast",
        {"fd": str(today),
         "bs": src_session or str(today),
         "bst": None, "t": json.dumps(tape, default=str),
         "o": json.dumps(overnight, default=str),
         "f": json.dumps(fc, default=str)})
    return {"forecast_date": str(today), "score": fc["direction_score"],
            "band": fc["band"], "overnight": overnight}


def grade() -> dict[str, int]:
    """Score the call: did the target session move the way the score
    leaned? ≥55 bullish / ≤45 bearish vs QQQ close-over-prior-close."""
    from app.database import db
    rows = db.execute_query(
        "SELECT id, forecast_date, stage, forecast FROM session_forecasts"
        " WHERE graded_at IS NULL AND forecast_date < CURRENT_DATE"
        " LIMIT 60")
    graded = 0
    for r in rows:
        d = r["forecast_date"]
        bars = db.execute_query(
            "SELECT date, close FROM daily_bars WHERE symbol='QQQ'"
            " AND date<=:d ORDER BY date DESC LIMIT 2", {"d": d})
        if len(bars) < 2 or bars[0]["date"] != d:
            continue
        ret = float(bars[0]["close"]) / float(bars[1]["close"]) - 1
        fc = r["forecast"] or {}
        if isinstance(fc, str):
            fc = json.loads(fc)
        s = fc.get("direction_score")
        hit = (None if s is None else
               (ret > 0) if s >= 55 else (ret < 0) if s <= 45 else None)
        db.execute_update(
            "UPDATE session_forecasts SET actual_ret=:r, hit=:h,"
            " graded_at=NOW() WHERE id=:i",
            {"r": round(float(ret), 4), "h": hit, "i": r["id"]})
        graded += 1
    return {"graded": graded}


def latest() -> dict[str, Any]:
    """Forecast rows for the nearest target session — the card read."""
    from app.database import db
    rows = db.execute_query(
        "SELECT forecast_date, baseline_session, baseline_session_type,"
        " stage, tape, overnight, forecast, actual_ret, hit, created_at"
        " FROM session_forecasts"
        " WHERE forecast_date >= CURRENT_DATE - 7"
        " ORDER BY forecast_date DESC, stage LIMIT 10")
    out: dict[str, Any] = {"rows": []}
    for r in rows:
        for k in ("tape", "overnight", "forecast"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
        r["created_at"] = str(r["created_at"])
        r["forecast_date"] = str(r["forecast_date"])
        r["baseline_session"] = str(r["baseline_session"])
        out["rows"].append(r)
    return out


def run() -> dict[str, Any]:
    """Job entry — stage follows the clock; grading always sweeps."""
    from app.database import db          # noqa: F401  (db availability)
    now = datetime.now(_ET)
    out: dict[str, Any] = {}
    try:
        out["graded"] = grade()["graded"]
    except Exception as e:                                  # noqa: BLE001
        logger.debug("grade: %s", e)
    try:
        if now.time() >= dtime(16, 5) and now.weekday() < 5:
            out["baseline"] = baseline()
        elif dtime(4, 0) <= now.time() <= dtime(9, 30) \
                and now.weekday() < 5:
            out["premarket"] = premarket()
        else:
            out["skipped"] = "outside stage window"
    except Exception as e:                                  # noqa: BLE001
        logger.warning("session_forecast: %s", e)
        out["error"] = str(e)[:200]
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=str))
