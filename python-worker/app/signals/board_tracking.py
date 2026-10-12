"""Board accountability — snapshot every published pick, grade it later.

The desk pattern: you can't improve what you don't grade. Each day's
board rows are persisted with spot + plan levels; a daily evaluator
fills forward returns at 5/10/20 trading days (ret / MFE / MAE — the
same shape alert_outcomes uses). track_record() then answers the only
question that matters: which action × momentum combos actually paid.

  snapshot_board(board)   idempotent per (date, symbol, action)
  evaluate_pending()      fills board_outcomes — safe to run daily
  track_record()          accuracy stats for the UI strip
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

HORIZONS = (5, 10, 20)
# LEAPS actions get the months-long window — a 6-24mo instrument can't
# be graded on a 20d read; 40/60 trading days ≈ 2/3 months out.
LEAPS_HORIZONS = (5, 10, 20, 40, 60)


def _horizons_for(instrument: Optional[str]) -> tuple:
    return (LEAPS_HORIZONS
            if instrument and "LEAPS" in instrument.upper()
            else HORIZONS)


def snapshot_board(board: dict) -> int:
    """Persist today's published picks. Idempotent — re-rendering the
    page never double-writes. Spot price comes from the screen item when
    the board carries it, else stays NULL and the evaluator anchors on
    the decision day's close."""
    from app.database import db
    today = date.today()
    n = 0
    for it in board.get("items") or []:
        try:
            db.execute_update(
                """
                INSERT INTO board_decisions
                    (as_of, symbol, action, instrument, score,
                     momentum_state, posture, price, entry, stop,
                     target, evidence)
                VALUES (:d, :s, :a, :i, :sc, :m, :p, :px, :e, :st, :t,
                        CAST(:ev AS jsonb))
                ON CONFLICT (as_of, symbol, action) DO NOTHING
                """,
                {"d": today, "s": it["symbol"], "a": it["action"],
                 "i": it.get("instrument"), "sc": it.get("score"),
                 "m": it.get("momentum"),
                 "p": (board.get("posture") or {}).get("stance"),
                 "px": it.get("price"), "e": it.get("entry"),
                 "st": it.get("stop"), "t": it.get("target"),
                 "ev": __import__("json").dumps(it.get("why") or [])})
            n += 1
        except Exception as exc:
            logger.debug("board snapshot %s: %s", it.get("symbol"), exc)
    return n


def _bars(sym: str, start: date):
    """Daily bars since the decision — same batched-yf shape used
    elsewhere in the codebase."""
    import yfinance as yf
    from types import SimpleNamespace
    d = yf.download(sym, start=start.isoformat(), interval="1d",
                    group_by="ticker", progress=False, auto_adjust=True)
    try:
        sub = d[sym]
    except (KeyError, TypeError):
        sub = d
    sub = sub.dropna(subset=["Close"])
    return [SimpleNamespace(timestamp=i.to_pydatetime(),
                            open=float(r.Open), high=float(r.High),
                            low=float(r.Low), close=float(r.Close))
            for i, r in sub.iterrows()]


def evaluate_pending(max_symbols: int = 400) -> dict:
    """Fill forward outcomes for published decisions. Anchored on the
    decision-day close (price stored at snapshot, else first bar) and
    measured strictly after it — weekend decisions anchor Monday."""
    from app.database import db
    rows = db.execute_query(
        """
        SELECT d.id, d.symbol, d.as_of, d.price, d.action, d.instrument
        FROM board_decisions d
        WHERE NOT EXISTS (
            SELECT 1 FROM board_outcomes o
            WHERE o.decision_id = d.id
              AND o.horizon_days = CASE
                  WHEN d.instrument ILIKE '%LEAPS%' THEN 60
                  ELSE 20 END)
        ORDER BY d.as_of DESC
        LIMIT :n
        """,
        {"n": max_symbols})
    done, errors = 0, []
    for d in rows:
        try:
            bars = _bars(d["symbol"], d["as_of"])
            if not bars:
                continue
            anchor = bars[0]
            entry = float(d["price"] or anchor.close)
            # direction-aware: PUT/EXIT benefit from declines — flip the
            # return so "good" is positive regardless of side
            sign = -1.0 if d["action"] in ("PUT", "EXIT") else 1.0
            forward = [b for b in bars
                       if b.timestamp.date() > anchor.timestamp.date()]
            if not forward:
                continue
            for h in _horizons_for(d.get("instrument")):
                w = forward[:h]
                if len(w) < min(h, 2):
                    continue
                ret = (w[-1].close - entry) / entry * 100 * sign
                mfe = (max(b.high for b in w) / entry - 1) * 100 * sign
                mae = (min(b.low for b in w) / entry - 1) * 100 * sign
                db.execute_update(
                    """
                    INSERT INTO board_outcomes
                        (decision_id, horizon_days, ret_pct, mfe_pct,
                         mae_pct)
                    VALUES (:i, :h, :r, :mfe, :mae)
                    ON CONFLICT (decision_id, horizon_days) DO NOTHING
                    """,
                    {"i": d["id"], "h": h, "r": round(ret, 2),
                     "mfe": round(mfe, 2), "mae": round(mae, 2)})
            done += 1
        except Exception as exc:
            errors.append(f"{d['symbol']}: {exc}")
    return {"evaluated": done, "errors": errors[:10]}


def track_record() -> dict:
    """Accuracy by action and by momentum state — the learning output.
    Returns per-cell {n, avg_ret, hit_rate} at each horizon."""
    from app.database import db
    rows = db.execute_query(
        """
        SELECT d.action, d.momentum_state, o.horizon_days,
               count(*) n,
               round(avg(o.ret_pct), 2) avg_ret,
               round(avg(o.mfe_pct), 2) avg_mfe,
               round(avg(o.mae_pct), 2) avg_mae,
               round(100.0 * avg(CASE WHEN o.ret_pct > 0
                                THEN 1 ELSE 0 END), 0) hit_rate
        FROM board_decisions d
        JOIN board_outcomes o ON o.decision_id = d.id
        GROUP BY d.action, d.momentum_state, o.horizon_days
        ORDER BY d.action, d.momentum_state, o.horizon_days
        """)
    return {"cells": rows,
            "evaluated_decisions": len({r["n"] for r in rows}) and
                db.execute_query(
                    "SELECT count(*) AS n FROM board_decisions")[0]["n"]}


def snapshot_regime(posture: dict) -> bool:
    """Journal the day's regime read — forward probs, dip character,
    allocation stance. Idempotent per day; the grader fills realized
    SPY returns so meta can calibrate the forward heuristic."""
    if not posture:
        return False
    from app.database import db
    import json
    fw = posture.get("forward") or {}
    dc = posture.get("dip_character") or {}
    al = posture.get("allocation") or {}
    try:
        db.execute_update(
            """
            INSERT INTO regime_snapshots
                (as_of, stance, vix, spy_vs_200, p_deeper, p_chop,
                 p_bull, lead_scenario, dip_character, ai_rs20,
                 cash_buffer, payload)
            VALUES (:d, :st, :v, :s2, :pd, :pc, :pb, :lead, :dc,
                    :rs, :cb, CAST(:p AS jsonb))
            ON CONFLICT (as_of) DO NOTHING
            """,
            {"d": date.today(), "st": posture.get("stance"),
             "v": posture.get("vix"),
             "s2": posture.get("spy_vs_200"),
             "pd": fw.get("p_deeper_dip_20d"),
             "pc": fw.get("p_chop_20d"), "pb": fw.get("p_bullish_20d"),
             "lead": fw.get("lead_scenario"),
             "dc": dc.get("character"), "rs": dc.get("ai_rs20"),
             "cb": al.get("cash_buffer_pct"),
             "p": json.dumps(posture, default=str)})
        return True
    except Exception as exc:
        logger.debug("regime snapshot failed: %s", exc)
        return False


def evaluate_regime(days_back: int = 120) -> dict:
    """Grade journaled regime reads: realized SPY return at 20/60
    trading days + whether the lead scenario matched. 'dip' is correct
    if SPY fell >1%, 'growth' if it rose >1%, 'chop' in between."""
    from app.database import db
    rows = db.execute_query(
        """SELECT id, as_of, lead_scenario, spy_ret_20d, spy_ret_60d
           FROM regime_snapshots
           WHERE as_of > now()::date - :d
             AND (spy_ret_20d IS NULL OR spy_ret_60d IS NULL)""",
        {"d": days_back})
    done = 0
    spy_cache: dict = {}
    for r in rows:
        try:
            if r["as_of"] not in spy_cache:
                spy_cache[r["as_of"]] = _bars("SPY", r["as_of"])
            bars = spy_cache[r["as_of"]]
            fwd = [b for b in bars
                   if b.timestamp.date() > r["as_of"]]
            if len(fwd) < 5:
                continue
            entry = bars[0].close
            r20 = (round((fwd[19].close / entry - 1) * 100, 2)
                   if len(fwd) >= 20 else None)
            r60 = (round((fwd[59].close / entry - 1) * 100, 2)
                   if len(fwd) >= 60 else None)
            lead_ok = None
            if r20 is not None and r["lead_scenario"]:
                lead_ok = ({"dip": r20 < -1.0,
                            "growth": r20 > 1.0}
                           .get(r["lead_scenario"], abs(r20) <= 1.0))
            db.execute_update(
                """UPDATE regime_snapshots SET
                    spy_ret_20d=COALESCE(:r20, spy_ret_20d),
                    spy_ret_60d=COALESCE(:r60, spy_ret_60d),
                    lead_correct=COALESCE(:ok, lead_correct),
                    graded_at=now() WHERE id=:i""",
                {"r20": r20, "r60": r60, "ok": lead_ok, "i": r["id"]})
            done += 1
        except Exception as exc:
            logger.debug("regime grade %s: %s", r["as_of"], exc)
    return {"evaluated": done}


def instrument_record() -> dict:
    """Did the instrument suggestions work — LEAPS calls/puts vs stock
    actions, per horizon. The 'were we right' ledger for the board's
    ~10 daily actions."""
    from app.database import db
    rows = db.execute_query(
        """
        SELECT CASE WHEN d.instrument ILIKE '%LEAPS call%' THEN 'LEAPS call'
                    WHEN d.instrument ILIKE '%LEAPS put%' THEN 'LEAPS put'
                    WHEN d.instrument ILIKE '%LEAPS%' THEN 'LEAPS'
                    ELSE COALESCE(d.instrument, 'stock') END inst,
               d.action, o.horizon_days, count(*) n,
               round(avg(o.ret_pct)::numeric, 2) avg_ret,
               round(100.0 * avg(CASE WHEN o.ret_pct > 0
                    THEN 1 ELSE 0 END)::numeric, 0) hit_rate
        FROM board_decisions d
        JOIN board_outcomes o ON o.decision_id = d.id
        GROUP BY 1, d.action, o.horizon_days
        ORDER BY 1, d.action, o.horizon_days
        """)
    pending = db.execute_query(
        """SELECT instrument, count(*) n FROM board_decisions
           GROUP BY instrument""")
    return {"cells": rows, "journaled": pending}


def regime_record() -> dict:
    """Regime calibration — journaled forward reads vs realized SPY.
    'lead accuracy' = the scenario we named most-likely was the one
    that played out over the next 20 sessions."""
    from app.database import db
    rows = db.execute_query(
        """SELECT lead_scenario, dip_character, count(*) n,
                  round(avg(spy_ret_20d)::numeric, 2) avg_spy_20d,
                  round(100.0 * avg(CASE WHEN lead_correct
                        THEN 1 ELSE 0 END)::numeric, 0) lead_hit
           FROM regime_snapshots
           WHERE spy_ret_20d IS NOT NULL
           GROUP BY lead_scenario, dip_character
           ORDER BY 1, 2""")
    total = db.execute_query(
        """SELECT count(*) n,
                  count(*) FILTER (WHERE spy_ret_20d IS NOT NULL) graded,
                  round(100.0 * avg(CASE WHEN lead_correct
                        THEN 1 ELSE 0 END)::numeric, 0) overall_hit
           FROM regime_snapshots""")
    return {"cells": rows, "summary": total[0] if total else {}}
