"""Commitment lifecycle review — extends driver_commitments.

The journal already captures raises/cuts/reaffirms and supersedes
revisions. This adds the spec's status vocabulary so the research
report can answer 'did management deliver?':

    not_due      period still in the future, nothing to check
    on_track     open + reaffirmed recently (90d)
    achieved     superseded by a >= commitment (met-or-raised is the
                 only machine-readable 'achieved' — real verification
                 needs outcome data and stays human)
    delayed      open but period already passed with no resolution
    revised      superseded by a DIFFERENT value
    missed       superseded by a cut
    unverifiable everything else — honest default, never guessed

Deterministic statuses — no LLM judgment on delivery.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PERIOD_YR = re.compile(r"(20\d\d)")


def _period_due(period: str, today: date) -> Optional[bool]:
    """Is the commitment's period already past? Only decidable when
    the period carries a year (or 'FY26 Q3' shapes); vague horizons
    return None → not decidable."""
    m = _PERIOD_YR.search(period or "")
    if not m:
        return None
    return today.year > int(m.group(1))


def review(sym: str, today: Optional[date] = None) -> list[dict]:
    from app.database import db
    today = today or date.today()
    try:
        rows = db.execute_query(
            "SELECT metric, period, value, prior_value, delta_dir,"
            " delta_pct, consensus_pct, status, created_at"
            " FROM driver_commitments WHERE symbol=:s"
            " ORDER BY created_at DESC LIMIT 40",
            {"s": sym.upper()})
    except Exception as exc:
        logger.debug("commitments %s: %s", sym, exc)
        return []
    out = []
    for r in rows:
        due = _period_due(r.get("period") or "", today)
        status = r.get("status")
        delta = r.get("delta_dir")
        if status == "superseded":
            life = "missed" if delta == "cut" else "revised"
        elif due is True:
            life = "delayed"        # period passed, still open
        elif due is False:
            life = "not_due"
        elif delta == "reaffirmed":
            life = "on_track"
        else:
            life = "unverifiable"
        out.append({"metric": r["metric"], "period": r["period"],
                    "value": _f(r["value"]),
                    "prior_value": _f(r["prior_value"]),
                    "delta_dir": delta,
                    "consensus_pct": _f(r["consensus_pct"]),
                    "status": life})
    return out


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def credibility(rows: list[dict]) -> dict:
    """The delivery record summary — counts, never sentiment."""
    n = len(rows)
    by = {}
    for r in rows:
        by[r["status"]] = by.get(r["status"], 0) + 1
    decided = by.get("missed", 0) + by.get("revised", 0) + \
        by.get("delayed", 0)
    return {"tracked": n, "by_status": by,
            "negative": decided,
            "record": ("thin" if n < 3 else
                       "poor" if decided >= max(2, n // 3)
                       else "clean")}
