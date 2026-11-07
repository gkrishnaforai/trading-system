"""Hourly intraday regime overlay — timing context over the daily regime.

The morning regime remains the journaled daily baseline. This layer
reuses the 15-minute tape classifier and journals a timestamped read
so the page can distinguish "baseline still valid" from "tape says
pause entries right now" without rewriting daily history.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def _baseline() -> dict[str, Any]:
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, regime, score FROM morning_regime_snapshots"
        " ORDER BY as_of DESC LIMIT 1")
    if not rows:
        return {}
    row = dict(rows[0])
    row["as_of"] = str(row.get("as_of"))
    return row


def _overlay(baseline_regime: str | None,
             tape_state: str | None) -> dict[str, str]:
    """Deterministic baseline × tape timing decision."""
    risk_on = baseline_regime in ("strong_risk_on", "risk_on")
    risk_off = baseline_regime in ("risk_off", "stress")
    if not baseline_regime:
        return {"state": "no_baseline",
                "action": "no daily regime baseline — fail closed",
                "tone": "off"}
    if risk_off:
        return {"state": "defensive",
                "action": "daily regime is defensive — intraday strength is not an add signal",
                "tone": "bad"}
    if tape_state == "buyers_in_control":
        return {"state": "aligned",
                "action": "baseline and tape agree — staged adds remain permitted",
                "tone": "good" if risk_on else "warn"}
    if tape_state == "sellers_regaining":
        return {"state": "tape_breaking",
                "action": "pause new adds — VWAP/breadth/VIX must repair",
                "tone": "bad"}
    if tape_state == "narrow_fragile":
        return {"state": "fragile",
                "action": "no chasing — strength is too narrow to add risk",
                "tone": "warn"}
    if tape_state == "sellers_exhausting":
        return {"state": "watch_reversal",
                "action": "sellers are tiring — watch for confirmation, do not front-run",
                "tone": "warn"}
    if tape_state == "chop_unconfirmed":
        return {"state": "unconfirmed",
                "action": "baseline unchanged — tape is not confirming entries",
                "tone": "warn"}
    return {"state": "baseline_only",
            "action": "no usable intraday tape read — daily baseline remains in force",
            "tone": "off"}


def snapshot() -> dict[str, Any]:
    """Journal the current overlay. Called hourly 8:00-17:00 ET."""
    from app.database import db
    from app.signals import intraday_pulse as ip

    baseline = _baseline()
    tape = ip.evaluate() if ip.market_open_now() else ip.latest()
    eval_ = tape.get("eval") if isinstance(tape.get("eval"), dict) else {}
    tape_state = str(tape.get("state") or "no_data")
    overlay = _overlay(baseline.get("regime"), tape_state)
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc.astimezone(_ET)
    out = {
        "as_of": now_utc.isoformat(timespec="seconds"),
        "session_date": now_et.date().isoformat(),
        "market_time": now_et.isoformat(timespec="seconds"),
        "baseline_as_of": baseline.get("as_of"),
        "baseline_regime": baseline.get("regime"),
        "baseline_score": baseline.get("score"),
        "tape_state": tape_state,
        "tape_ts": tape.get("ts"),
        "state": overlay["state"],
        "action": overlay["action"],
        "tone": overlay["tone"],
        "evidence": {
            "tape": eval_.get("evidence") or [],
            "qqq_chg_open": eval_.get("qqq_chg_open"),
            "spy_chg_open": eval_.get("spy_chg_open"),
            "vix": eval_.get("vix"),
            "breadth_adv_pct": eval_.get("breadth_adv_pct"),
            "leadership": eval_.get("leadership"),
            "macro_pressure": eval_.get("macro_pressure"),
            "prob_close_green": eval_.get("prob_close_green"),
            "day_type": eval_.get("day_type"),
            "tradeability": eval_.get("tradeability"),
            "tradeability_cls": eval_.get("tradeability_cls"),
            "strategy_permissions": eval_.get("strategy_permissions"),
        },
    }
    db.execute_update(
        "INSERT INTO regime_intraday_snapshots"
        " (as_of, session_date, market_time, baseline_as_of,"
        "  baseline_regime, baseline_score, tape_state, tape_ts,"
        "  state, action, tone, evidence)"
        " VALUES (:as_of,:sd,:mt,:bas,:br,:bs,:ts,:tts,:st,:act,:tn,"
        " CAST(:ev AS jsonb))"
        " ON CONFLICT (as_of) DO UPDATE SET"
        " market_time=EXCLUDED.market_time,"
        " baseline_as_of=EXCLUDED.baseline_as_of,"
        " baseline_regime=EXCLUDED.baseline_regime,"
        " baseline_score=EXCLUDED.baseline_score,"
        " tape_state=EXCLUDED.tape_state, tape_ts=EXCLUDED.tape_ts,"
        " state=EXCLUDED.state, action=EXCLUDED.action,"
        " tone=EXCLUDED.tone, evidence=EXCLUDED.evidence",
        {"as_of": out["as_of"], "sd": out["session_date"],
         "mt": out["market_time"], "bas": out["baseline_as_of"],
         "br": out["baseline_regime"], "bs": out["baseline_score"],
         "ts": out["tape_state"], "tts": out["tape_ts"],
         "st": out["state"], "act": out["action"],
         "tn": out["tone"], "ev": json.dumps(out["evidence"], default=str)})
    return out


def latest() -> dict[str, Any] | None:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT as_of, session_date, market_time, baseline_as_of,"
            " baseline_regime, baseline_score, tape_state, tape_ts,"
            " state, action, tone, evidence"
            " FROM regime_intraday_snapshots"
            " ORDER BY as_of DESC LIMIT 1")
    except Exception:
        return None
    if not rows:
        return None
    row = dict(rows[0])
    ev = row.get("evidence")
    if isinstance(ev, str):
        try:
            row["evidence"] = json.loads(ev)
        except Exception:
            row["evidence"] = {}
    for k in ("as_of", "session_date", "market_time", "baseline_as_of",
              "tape_ts"):
        if row.get(k) is not None:
            row[k] = str(row[k])
    try:
        asof = datetime.fromisoformat(str(row["as_of"]))
        if asof.tzinfo is None:
            asof = asof.replace(tzinfo=timezone.utc)
        row["age_minutes"] = round(
            (datetime.now(timezone.utc)
             - asof.astimezone(timezone.utc)).total_seconds() / 60, 1)
    except Exception:
        row["age_minutes"] = None
    row["stale"] = (row.get("session_date")
                    != datetime.now(_ET).date().isoformat()) or         (row["age_minutes"] is not None and row["age_minutes"] > 75)
    return row
