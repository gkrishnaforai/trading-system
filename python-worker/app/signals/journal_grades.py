"""journal_grades — the weekly substrate→feedback bridge.

Every journal that emits states/stances/events gets graded the same
way alert_kind_stats grades alerts: forward returns at 5/10/20
trading days after each row, aggregated per bucket. The output is
journal_kind_stats — the honest scoreboard for "did that signal
actually precede the move it claimed to see".

Grading is descriptive, not prescriptive: stats are written with
n + reliability flags; nothing here rewrites engine weights. The
bounded-weight writes stay in meta_learn's lane.

Journals graded (Phase 1 of the loop):
  recovery_verdicts.state          EXHAUSTION→RECOVERY vs fwd rets
  thesis_change_events.status      transition targets vs fwd rets
  crypto_positioning_daily.stance  accumulation/distribution vs BTC
  selloff_candidates.classification dislocation type vs fwd rets
  insider_transactions cluster rows (P buys) vs fwd rets
"""
from __future__ import annotations

import logging
import statistics as st
from typing import Any

logger = logging.getLogger(__name__)

HORIZONS = (5, 10, 20)
_MIN_RELIABLE = 20

# kind → (row source, symbol expr, bucket expr, maturity gate)
_JOURNALS: dict[str, dict] = {
    "recovery_state": {
        "sql": """SELECT symbol, as_of, state AS bucket
                  FROM recovery_verdicts WHERE state_changed
                  AND event_type IS NOT NULL OR state != 'NORMAL'""",
    },
    "thesis_transition": {
        "sql": """SELECT symbol, as_of, status AS bucket
                  FROM thesis_change_events
                  WHERE event_kind = 'status_transition'""",
    },
    "crypto_stance": {
        "sql": """SELECT 'BTC-USD' AS symbol, as_of, stance AS bucket
                  FROM crypto_positioning_daily
                  WHERE stance IS NOT NULL""",
    },
    "selloff_class": {
        "sql": """SELECT symbol, as_of,
                  classification AS bucket
                  FROM selloff_candidates
                  WHERE classification IS NOT NULL""",
    },
    "insider_cluster": {
        "sql": """SELECT symbol, transaction_date AS as_of,
                  'buy_cluster' AS bucket
                  FROM insider_transactions
                  WHERE transaction_code = 'P'""",
    },
    "valuation_decision": {
        "sql": """SELECT symbol, as_of, decision AS bucket
                  FROM valuation_decisions
                  WHERE decision IS NOT NULL""",
    },
    "priced_in_band": {
        "sql": """SELECT symbol, as_of, band AS bucket
                  FROM valuation_decisions
                  WHERE band IS NOT NULL""",
    },
}


def _fwd(sym: str, as_of: str, days: int) -> Any:
    """Close on/as of the row date → first close on/after as_of+days
    (calendar-day approximation — same as the alert-outcome grader)."""
    from app.database import db
    rows = db.execute_query(
        "SELECT "
        " (SELECT close FROM daily_bars WHERE symbol=:s"
        "  AND date <= CAST(:d AS date) ORDER BY date DESC LIMIT 1)"
        "  AS base,"
        " (SELECT close FROM daily_bars WHERE symbol=:s"
        "  AND date >= CAST(:d AS date) + (:h * INTERVAL '1 day')"
        "  ORDER BY date LIMIT 1) AS fwd",
        {"s": sym, "d": str(as_of)[:10], "h": days})
    if not rows or rows[0].get("base") in (None, 0) \
            or rows[0].get("fwd") is None:
        return None
    return (float(rows[0]["fwd"]) / float(rows[0]["base"]) - 1) * 100


def _grade_rows(rows: list[dict]) -> dict[tuple, dict]:
    """(kind, bucket, horizon) → stats over matured rows."""
    acc: dict[tuple, list] = {}
    for r in rows:
        for h in HORIZONS:
            ret = _fwd(r["symbol"], r["as_of"], h)
            if ret is None:
                continue
            acc.setdefault((r["_kind"], r["bucket"], h),
                           []).append(ret)
    out = {}
    for (kind, bucket, h), rets in acc.items():
        out[(kind, bucket, h)] = {
            "n": len(rets),
            "win_rate": round(sum(1 for x in rets if x > 0)
                              / len(rets) * 100, 1),
            "avg_ret": round(sum(rets) / len(rets), 2),
            "median_ret": round(st.median(rets), 2),
            "reliable": len(rets) >= _MIN_RELIABLE,
        }
    return out


def run() -> dict:
    """Grade every journal, rewrite journal_kind_stats."""
    from app.database import db
    all_rows, errs = [], []
    for kind, spec in _JOURNALS.items():
        try:
            rows = db.execute_query(spec["sql"]) or []
            for r in rows:
                r["_kind"] = kind
            all_rows.extend(rows)
        except Exception as e:          # table may not exist yet
            errs.append(f"{kind}: {e}")
    stats = _grade_rows(all_rows)

    db.execute_update("DELETE FROM journal_kind_stats")
    for (kind, bucket, h), s in stats.items():
        db.execute_update(
            "INSERT INTO journal_kind_stats (kind, bucket, horizon,"
            " n, win_rate, avg_ret, median_ret, reliable, graded_at)"
            " VALUES (:k,:b,:h,:n,:w,:a,:m,:r,now())",
            {"k": kind, "b": bucket, "h": h, "n": s["n"],
             "w": s["win_rate"], "a": s["avg_ret"],
             "m": s["median_ret"], "r": s["reliable"]})

    by_kind: dict[str, dict] = {}
    for (kind, bucket, h), s in stats.items():
        k = by_kind.setdefault(kind, {"buckets": 0, "n": 0,
                                      "reliable": 0})
        k["buckets"] += 1
        k["n"] += s["n"]
        k["reliable"] += int(s["reliable"])
    report = {"rows_scanned": len(all_rows), "stats_written": len(stats),
              "by_kind": by_kind, "errors": errs}
    db.execute_update(
        "INSERT INTO engine_weights (key, value, updated_at)"
        " VALUES ('journal_grades:report', CAST(:v AS jsonb), now())"
        " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,"
        " updated_at=now()",
        {"v": __import__("json").dumps(report, default=str)})
    logger.info("journal_grades: %s", report)
    return report


def read(kind: str | None = None) -> list[dict]:
    from app.database import db
    q = ("SELECT * FROM journal_kind_stats"
         + (" WHERE kind=:k" if kind else "")
         + " ORDER BY kind, bucket, horizon")
    return db.execute_query(q, {"k": kind} if kind else {}) or []
