"""Selloff learning loop — did the beaten-down picks actually rebound?

Three passes:

  grade()   daily (folded into the outcomes job) — every journaled
            selloff_candidates row gets forward outcomes measured
            from its as_of close: returns at 5/10/20d, QQQ-relative
            returns, rebound-speed metrics (days to +10%, days to
            MFE, days underwater). Grades ALL journaled candidates,
            not just the published top-10 — a low-ranked winner is
            exactly what the loop needs to catch.

  review()  attribution — cohort stats by sbd_class / decision /
            session-entry action / pf_gap bucket, plus the fastest
            rebounders with their signal-time features. Answers
            "which stock bounced back fast, and why the engine saw
            it coming (or didn't)".

  report()  journaled inside grade() — the review plus bounded
            weight-correction suggestions → selloff_engine_reports.
            Advisory only: the engine never rewrites its own
            weights; every suggestion carries the n it stands on.
            decision_weight stays 0 — same shadow discipline as the
            forward/stability engines.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

_HORIZONS = (5, 10, 20)
_GRADE_WINDOW_D = 120          # candidates older than this are settled
_MIN_COHORT_N = 8              # a cohort needs this many grades to advise
_SEPARATION_PP = 4.0           # min rel_ret_10d gap to suggest a change
_MAX_WEIGHT_SUGGEST = 15       # ±% cap on any single suggestion


def _bars(sym: str, start: date):
    from app.signals.board_tracking import _bars as _b
    return _b(sym, start)


def _session_entry(sym: str, as_of: date) -> dict:
    """The stability job's close-mark verdict for this candidate on its
    signal day — starter/add/wait + accumulation score. Missing = the
    job hadn't run or the name wasn't scored; never fabricated."""
    from app.database import db
    rows = db.execute_query(
        "SELECT readings->'session_entries' AS se"
        " FROM market_stability_snapshots"
        " WHERE session_date = :d AND mark = 'close'"
        " LIMIT 1", {"d": as_of})
    if not rows or not rows[0].get("se"):
        return {}
    se = rows[0]["se"]
    if isinstance(se, str):
        se = json.loads(se)
    e = ((se or {}).get("entries") or {}).get(sym) or {}
    return {"action": e.get("suggested_action"),
            "sas": e.get("stock_accumulation_score"),
            "mss": se.get("market_stability_score")}


def _grade_row(c: dict, bars, qqq_bars) -> dict:
    """One candidate → one grades row, filled as far as the tape has
    gone. Progressive: a 3-day-old signal already shows its 5d lean."""
    anchor_ts = next((b for b in bars
                      if b.timestamp.date() >= c["as_of"]), None)
    if anchor_ts is None:
        return {}
    anchor = anchor_ts.close
    if not anchor:
        return {}
    fwd = [b for b in bars if b.timestamp.date() > anchor_ts.timestamp.date()]
    qfwd = {b.timestamp.date(): b.close for b in qqq_bars
            if b.timestamp.date() > anchor_ts.timestamp.date()}
    qanchor_ts = next((b for b in qqq_bars
                       if b.timestamp.date() >= c["as_of"]), None)
    out: dict[str, Any] = {}
    for h in _HORIZONS:
        w = fwd[:h]
        if len(w) < min(h, 2):
            continue
        close = w[-1].close
        ret = (close / anchor - 1) * 100
        out[f"ret_{h}d"] = round(ret, 2)
        if h in (10, 20) and qanchor_ts and len(qfwd) >= min(h, 2):
            qd = w[-1].timestamp.date()
            qb = [v for d_, v in sorted(qfwd.items()) if d_ <= qd]
            if qb:
                qret = (qb[-1] / qanchor_ts.close - 1) * 100
                out[f"rel_ret_{h}d"] = round(ret - qret, 2)
    w20 = fwd[:20]
    if w20:
        closes = [(b.timestamp.date(), b.close) for b in w20]
        mfe_i, mfe = max(enumerate(closes), key=lambda t: t[1][1])
        out["mfe_20d"] = round((mfe[1] / anchor - 1) * 100, 2)
        out["days_to_mfe"] = mfe_i + 1
        out["mae_20d"] = round(
            (min(c_ for _, c_ in closes) / anchor - 1) * 100, 2)
        out["days_underwater"] = sum(1 for _, c_ in closes
                                     if c_ < anchor)
        p10 = next((i + 1 for i, (_, c_) in enumerate(closes)
                    if c_ >= anchor * 1.10), None)
        out["days_to_plus10"] = p10
    return out


def grade(today: Optional[date] = None) -> dict:
    """Fill selloff_grades for every journaled candidate whose forward
    window has new tape. Idempotent — reruns only refresh rows whose
    20d read isn't final yet."""
    from app.database import db
    today = today or date.today()
    rows = db.execute_query(
        """
        SELECT c.as_of, c.symbol, c.decision,
               c.fund->'sbd'->>'class'        AS sbd_class,
               (c.fund->>'pf_gap')::numeric  AS pf_gap,
               g.ret_20d                     AS done
        FROM selloff_candidates c
        LEFT JOIN selloff_grades g
          ON g.as_of = c.as_of AND g.symbol = c.symbol
        WHERE c.as_of > :cutoff AND c.as_of <= :today
          AND g.ret_20d IS NULL
        ORDER BY c.as_of DESC
        LIMIT 400
        """, {"cutoff": today - timedelta(days=_GRADE_WINDOW_D),
              "today": today})
    if not rows:
        report()
        return {"graded": 0}
    cache: dict[str, list] = {}
    # one fetch per symbol, from its EARLIEST signal — a name journaled
    # on several days still grades the oldest rows correctly
    starts = {}
    for c in rows:
        starts[c["symbol"]] = min(starts.get(c["symbol"], c["as_of"]),
                                  c["as_of"])
    qqq = _bars("QQQ", min(r["as_of"] for r in rows))
    graded, errors = 0, []
    for c in rows:
        sym = c["symbol"]
        try:
            if sym not in cache:
                cache[sym] = _bars(sym, starts[sym])
            bars = [b for b in cache[sym]
                    if b.timestamp.date() >= c["as_of"]]
            if not bars:
                continue
            g = _grade_row(c, bars, qqq)
            if not g:
                continue
            se = _session_entry(sym, c["as_of"])
            db.execute_update(
                """
                INSERT INTO selloff_grades
                    (as_of, symbol, anchor_close, sbd_class, decision,
                     pf_gap, session_action, session_sas, session_mss,
                     ret_5d, ret_10d, ret_20d, rel_ret_10d, rel_ret_20d,
                     mfe_20d, mae_20d, days_to_mfe, days_to_plus10,
                     days_underwater)
                VALUES (:d,:s,:px,:sbd,:de,:gap,:sa,:sas,:mss,
                        :r5,:r10,:r20,:rel10,:rel20,:mfe,:mae,:dmfe,
                        :dp10,:duw)
                ON CONFLICT (as_of, symbol) DO UPDATE SET
                    ret_5d=EXCLUDED.ret_5d, ret_10d=EXCLUDED.ret_10d,
                    ret_20d=EXCLUDED.ret_20d,
                    rel_ret_10d=EXCLUDED.rel_ret_10d,
                    rel_ret_20d=EXCLUDED.rel_ret_20d,
                    mfe_20d=EXCLUDED.mfe_20d, mae_20d=EXCLUDED.mae_20d,
                    days_to_mfe=EXCLUDED.days_to_mfe,
                    days_to_plus10=EXCLUDED.days_to_plus10,
                    days_underwater=EXCLUDED.days_underwater,
                    session_action=EXCLUDED.session_action,
                    session_sas=EXCLUDED.session_sas,
                    session_mss=EXCLUDED.session_mss,
                    updated_at=now()
                """,
                {"d": c["as_of"], "s": sym,
                 "px": bars[0].close, "sbd": c.get("sbd_class"),
                 "de": c.get("decision"), "gap": c.get("pf_gap"),
                 "sa": se.get("action"), "sas": se.get("sas"),
                 "mss": se.get("mss"),
                 "r5": g.get("ret_5d"), "r10": g.get("ret_10d"),
                 "r20": g.get("ret_20d"),
                 "rel10": g.get("rel_ret_10d"),
                 "rel20": g.get("rel_ret_20d"),
                 "mfe": g.get("mfe_20d"), "mae": g.get("mae_20d"),
                 "dmfe": g.get("days_to_mfe"),
                 "dp10": g.get("days_to_plus10"),
                 "duw": g.get("days_underwater")})
            graded += 1
        except Exception as exc:
            errors.append(f"{sym}: {exc}")
            logger.debug("selloff grade %s: %s", sym, exc)
    rep = report()
    return {"graded": graded, "errors": errors[:10], "report": rep}


_COHORT_SQL = """
    SELECT {field} AS k, count(*) n,
           round(avg(rel_ret_10d), 2)   avg_rel10,
           round(avg(ret_20d), 2)      avg_ret20,
           round(avg(mae_20d), 2)      avg_mae,
           round(percentile_cont(0.5) WITHIN GROUP
                 (ORDER BY days_to_plus10)::numeric, 0) med_days_p10,
           round(100.0 * avg(CASE WHEN rel_ret_10d > 0
                  THEN 1 ELSE 0 END), 0) rel_hit10
    FROM selloff_grades
    WHERE {field} IS NOT NULL AND rel_ret_10d IS NOT NULL
    GROUP BY {field} ORDER BY avg_rel10 DESC NULLS LAST
"""


def review() -> dict:
    """Cohort attribution — which signal-time features separated the
    fast rebounders from the still-falling. Plus the fastest
    rebounders themselves with the evidence the engine held."""
    from app.database import db
    cohorts = {
        "by_sbd": db.execute_query(
            _COHORT_SQL.format(field="sbd_class")),
        "by_decision": db.execute_query(
            _COHORT_SQL.format(field="decision")),
        "by_session_entry": db.execute_query(
            _COHORT_SQL.format(field="session_action")),
        "by_pf_gap": db.execute_query(_COHORT_SQL.format(field="""
            CASE WHEN pf_gap <= -0.20 THEN 'deep(<-20%)'
                 WHEN pf_gap <= -0.10 THEN 'mid(-20..-10)'
                 WHEN pf_gap < 0     THEN 'shallow(-10..0)'
                 ELSE 'none(>=0)' END""")),
    }
    fastest = db.execute_query(
        """
        SELECT g.symbol, g.as_of, g.sbd_class, g.decision,
               g.session_action, g.session_sas, g.pf_gap,
               g.rel_ret_10d, g.mfe_20d, g.days_to_mfe,
               g.days_to_plus10, c.classification, c.score
        FROM selloff_grades g
        LEFT JOIN selloff_candidates c
          ON c.as_of = g.as_of AND c.symbol = g.symbol
        WHERE g.mfe_20d IS NOT NULL
        ORDER BY g.mfe_20d DESC NULLS LAST LIMIT 12
        """)
    n = db.execute_query("SELECT count(*) n FROM selloff_grades")[0]["n"]
    return {"n_graded": n, "cohorts": cohorts, "fastest": fastest}


def _suggestions(cohorts: dict) -> list[dict]:
    """Bounded corrections — never auto-applied. A suggestion needs a
    cohort of ≥_MIN_COHORT_N graded signals separating from the pack
    by ≥_SEPARATION_PP of QQQ-relative return at 10d. Small-n reads
    say so instead of pretending."""
    out: list[dict] = []
    from app.database import db
    r = db.execute_query(
        "SELECT round(avg(rel_ret_10d),2) m FROM selloff_grades"
        " WHERE rel_ret_10d IS NOT NULL")
    overall = (r[0]["m"] if r else None) or 0.0
    for field, rows in cohorts.items():
        for row in rows:
            n = row.get("n") or 0
            if n < _MIN_COHORT_N:
                continue
            gap = (row.get("avg_rel10") or 0) - overall
            if abs(gap) < _SEPARATION_PP:
                continue
            direction = "raise" if gap > 0 else "lower"
            out.append({
                "field": field, "value": row.get("k"),
                "n": n, "avg_rel10": row.get("avg_rel10"),
                "vs_overall_pp": round(gap, 2),
                "suggest": f"{direction} priority "
                           f"(cap ±{_MAX_WEIGHT_SUGGEST}%)",
                "confidence": "low" if n < 20 else "moderate"})
    return out


def report(today: Optional[date] = None) -> dict:
    """Journal the review + bounded suggestions. Upserts on as_of —
    the PIT record of what the evidence said and what it advised."""
    from app.database import db
    today = today or date.today()
    rv = review()
    if (rv.get("n_graded") or 0) < 5:
        return {"journaled": False, "n_graded": rv.get("n_graded")}
    rv["suggestions"] = _suggestions(rv["cohorts"])
    rv["calibration"] = {"mode": "shadow", "decision_weight": 0,
                         "note": "suggestions are advisory — weights "
                                 "change only by human commit"}
    db.execute_update(
        "INSERT INTO selloff_engine_reports (as_of, n_graded, report)"
        " VALUES (:d,:n,CAST(:r AS jsonb))"
        " ON CONFLICT (as_of) DO UPDATE SET n_graded=EXCLUDED.n_graded,"
        " report=EXCLUDED.report",
        {"d": today, "n": rv["n_graded"],
         "r": json.dumps(rv, default=str)})
    return {"journaled": True, "n_graded": rv["n_graded"],
            "suggestions": len(rv["suggestions"])}


def read_report() -> Optional[dict]:
    from app.database import db
    rows = db.execute_query(
        "SELECT as_of, n_graded, report FROM selloff_engine_reports"
        " ORDER BY as_of DESC LIMIT 1")
    if not rows:
        return None
    r = rows[0]
    rep = r["report"]
    if isinstance(rep, str):
        rep = json.loads(rep)
    return {"as_of": str(r["as_of"]), "n_graded": r["n_graded"],
            **(rep or {})}
