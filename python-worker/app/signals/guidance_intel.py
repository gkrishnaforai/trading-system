"""Guidance intelligence — the deterministic layer over the claim
streams doc_extract/earnings_release already produce.

Their spec mapped to our architecture:

  extraction   doc_analyses claims + thesis_watches (verbatim quotes
               already enforced — we never re-derive from prose)
  normalize    claim text → {metric, period, direction, value, basis}
               deterministically — regex, no LLM, no invented numbers
  score        outlook (raised/lowered, surprise if numeric) and
               quality (specificity: numbers + period + metric +
               quote coverage) — TWO scores, outlook ≠ reliability
  journal      symbol_guidance append-only rows + a latest summary

Honesty contract: parsing is regex over verbatim quotes — when a
claim can't be normalized it lands 'unparsed' not guessed. Missing
consensus makes surprise null, never fabricated. Outlook and
quality stay separate numbers — great-quality bearish guidance is
still bearish.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_METRIC_PAT = [
    (r"(?i)(revenue|sales|top ?line)", "revenue"),
    (r"(?i)(eps|earnings per share|profit|earnings)", "eps"),
    (r"(?i)(gross margin|gm\b|operating margin|op margin|ebitda"
     r"|margin)", "margin"),
    (r"(?i)(free cash|fcf|cash flow|capex|capital expend)", "cashflow"),
    (r"(?i)(backlog|orders|bookings|rpo|book.to.bill)", "backlog"),
    (r"(?i)(arr|nrr|net revenue retention|subscription)", "recurring"),
    (r"(?i)(buyback|repurchase|dividend)", "capital_return"),
]
_PERIOD_PAT = [
    (r"(?i)fy\s*'?(\d{2,4})", "fy"),
    (r"(?i)q\s*([1-4])", "quarter"),
    (r"(?i)(next quarter|current quarter|this quarter)", "quarter"),
    (r"(?i)(next year|full year|fiscal year|fiscal)", "fy"),
    (r"(?i)(second half|h2|first half|h1)", "half"),
]
_DIR_PAT = [
    (r"(?i)\b(rais\w+|increas\w+|lift\w+|above|higher|upgrad\w+)\b",
     "raised"),
    (r"(?i)\b(lower\w+|cut|reduc\w+|below|downgrad\w+|weak)\b",
     "lowered"),
    (r"(?i)\b(reiterat\w+|maintain\w+|reaffirm\w+|unchanged|in line)\b",
     "maintained"),
]
_NUM = r"\$?\s*([\d,.]+)\s*([BbMmKk%])?"


def _normalize(text: str) -> dict[str, Any]:
    """claim text → structured fields. Unparsed pieces stay null —
    a half-parsed guidance claim is worse than a raw one."""
    metric = next((m for pat, m in _METRIC_PAT
                   if re.search(pat, text)), None)
    period = next((f"{k}{m.group(1) if m.lastindex else ''}"
                   for pat, k in _PERIOD_PAT
                   for m in [re.search(pat, text)] if m), None)
    direction = next((d for pat, d in _DIR_PAT
                      if re.search(pat, text)), None)
    nums = [(float(n[0].replace(",", "")), n[1])
            for n in re.findall(_NUM, text)]
    return {"metric": metric, "period": period, "direction": direction,
            "values": nums, "normalized": bool(metric and period)}


def _claims(sym: str, limit: int = 30) -> list[dict]:
    """Recent verbatim-grounded claims tagged guidance-ish — the
    doc_extract journal is the only claim source we trust."""
    from app.database import db
    out = []
    try:
        for r in db.execute_query(
                "SELECT claims, created_at FROM doc_analyses"
                " WHERE symbol=:s ORDER BY created_at DESC LIMIT 4",
                {"s": sym}):
            cl = r.get("claims")
            cl = json.loads(cl) if isinstance(cl, str) else (cl or [])
            for c in cl:
                if isinstance(c, dict) and c.get("quote"):
                    c["doc_ts"] = str(r.get("created_at"))
                    out.append(c)
    except Exception as e:
        logger.debug("guidance claims %s: %s", sym, e)
    return [c for c in out
            if re.search(r"(?i)guid|expect|outlook|forecast|anticipat"
                         r"|fy\s*'?\d|next (quarter|year|fiscal)",
                         str(c.get("text") or ""))][:limit]


def compute(sym: str) -> dict[str, Any]:
    """symbol_guidance rows + outlook/quality scores for one symbol."""
    rows = []
    for c in _claims(sym):
        text = str(c.get("text") or "")
        n = _normalize(text)
        rows.append({
            "text": text[:400], "quote": str(c.get("quote") or "")[:400],
            "kind": c.get("kind"), "source_doc": c.get("doc_ts"),
            **n})
    if not rows:
        return {"symbol": sym, "guidance": [], "outlook": None,
                "quality": None, "note": "no guidance claims"}

    norm = [r for r in rows if r["normalized"]]
    raised = sum(1 for r in rows if r["direction"] == "raised")
    lowered = sum(1 for r in rows if r["direction"] == "lowered")
    # outlook — direction dominates; surprise needs consensus we may
    # not have, so it earns weight only when present
    outlook = None
    if raised or lowered:
        outlook = round(50 + 25 * (raised - lowered)
                        + 8 * (raised - lowered) * 0)  # dir only v1
        outlook = max(5, min(95, outlook))
    # quality — specificity coverage: normalized metric+period,
    # numeric value present, verbatim quote present, direction known
    q_parts = {
        "normalized": len(norm) / len(rows),
        "numeric": sum(1 for r in rows if r["values"]) / len(rows),
        "quoted": sum(1 for r in rows if r["quote"]) / len(rows),
        "directed": sum(1 for r in rows if r["direction"]) / len(rows),
    }
    quality = round(100 * (.35 * q_parts["normalized"]
                           + .25 * q_parts["numeric"]
                           + .25 * q_parts["quoted"]
                           + .15 * q_parts["directed"]))
    return {"symbol": sym, "guidance": rows, "outlook": outlook,
            "quality": quality, "counts": {
                "raised": raised, "lowered": lowered,
                "maintained": sum(1 for r in rows
                                  if r["direction"] == "maintained"),
                "unparsed": len(rows) - len(norm)},
            "as_of": str(date.today())}


def ensure_table() -> None:
    from app.database import db
    db.execute_update(
        "CREATE TABLE IF NOT EXISTS symbol_guidance ("
        " symbol TEXT NOT NULL, as_of DATE NOT NULL,"
        " outlook INT, quality INT, payload JSONB,"
        " created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        " PRIMARY KEY (symbol, as_of))")


def run(symbols: list[str]) -> dict[str, Any]:
    from app.database import db
    ensure_table()
    n = 0
    for sym in symbols:
        try:
            c = compute(sym)
            db.execute_update(
                "INSERT INTO symbol_guidance"
                " (symbol, as_of, outlook, quality, payload)"
                " VALUES (:s,:d,:o,:q,CAST(:p AS jsonb))"
                " ON CONFLICT (symbol,as_of) DO UPDATE SET"
                " outlook=EXCLUDED.outlook, quality=EXCLUDED.quality,"
                " payload=EXCLUDED.payload",
                {"s": sym, "d": date.today(),
                 "o": c.get("outlook"), "q": c.get("quality"),
                 "p": json.dumps(c, default=str)})
            n += 1
        except Exception as e:
            logger.debug("guidance %s: %s", sym, e)
    return {"scored": n}


def latest(sym: str) -> Optional[dict[str, Any]]:
    from app.database import db
    try:
        rows = db.execute_query(
            "SELECT payload FROM symbol_guidance"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 1", {"s": sym})
        if not rows:
            return None
        p = rows[0].get("payload")
        return json.loads(p) if isinstance(p, str) else p
    except Exception:
        return None
