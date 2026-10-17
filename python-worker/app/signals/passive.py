"""Passive-investor surface — the advisory overlay.

Three pieces:
  verdict   — the monthly DCA decision: buy / split / pause / deploy.
              Mapped deterministically from posture; the deploy hint
              is client-side (reserve bucket lives with the user).
  book      — a published model ETF allocation with a regime-driven
              tilt suggestion. The tilt is JOURNALED in passive_tilts
              so it can be graded like board calls — receipts for
              passive investing.
  context   — drawdown/regime read for the calm card.

Nothing executes. Regime sets aggressiveness, not picks — the tilt
moves between equity and ballast, never between named stocks.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# The published model book — a plain 3-bucket-plus-ballast core.
# VTI/VXUS are the engine, SGOV is the reserve proxy, GLD the hedge.
BASE_WEIGHTS = {"VTI": 60, "VXUS": 20, "SGOV": 12, "GLD": 8}
BOOK_NAME = "Core 80/20"
BOOK_NOTE = ("A boring core — US total market + international + T-bill "
             "reserve + gold. The tilt moves between engine and ballast; "
             "it never names a stock.")


def _q(sql: str, params: dict | None = None) -> list[dict]:
    from app.database import db
    return db.execute_query(sql, params or {})


def _bucket(posture: Optional[str]) -> str:
    p = (posture or "neutral").lower()
    if any(t in p for t in ("defens", "protect", "risk_off", "broken")):
        return "defensive"
    if any(t in p for t in ("aggress", "offens", "growth", "construct",
                            "risk_on", "deploy")):
        return "aggressive"
    return "neutral"


# Tilt table — weights must sum to 100. The ONLY degrees of freedom
# are how much sits in the engine (VTI+VXUS) vs ballast (SGOV+GLD).
_TILTS = {
    "aggressive": {
        "w": {"VTI": 62, "VXUS": 22, "SGOV": 9, "GLD": 7},
        "reason": ("tape constructive — run close to full engine. "
                   "Reserve stays at its floor; this is the month to "
                   "be boring at maximum weight.")},
    "neutral": {
        "w": {"VTI": 55, "VXUS": 19, "SGOV": 17, "GLD": 9},
        "reason": ("no edge either way — split the difference. A little "
                   "more ballast than base, contributions still buy.")},
    "defensive": {
        "w": {"VTI": 45, "VXUS": 15, "SGOV": 27, "GLD": 13},
        "reason": ("tape broken — don't force engine weight. New money "
                   "leans to the reserve sleeve until stabilization.")},
}


def _verdict(posture: Optional[str], new_longs: Optional[bool],
             prev_posture: Optional[str]) -> dict:
    """Monthly DCA verdict. Client composes 'deploy' when a reserve
    bucket exists — the server only says what THIS month is."""
    b = _bucket(posture)
    flipped = (prev_posture is not None
               and _bucket(prev_posture) == "defensive"
               and b != "defensive")
    if b == "defensive":
        return {"action": "pause", "tone": "defensive",
                "headline": "Pause the buy — hold it in reserve.",
                "note": ("The tape is broken; that's when automatic buys "
                         "hurt the least AND when saving them for "
                         "stabilization pays the most. Contribution goes "
                         "to the reserve bucket, not the index.")}
    if b == "aggressive":
        return {"action": "deploy" if flipped else "buy",
                "tone": "aggressive", "flipped": flipped,
                "headline": ("Regime flipped — deploy the reserve."
                             if flipped else "Buy as planned."),
                "note": ("The tape stabilized after a defensive stretch — "
                         "this is what the reserve bucket is for." if flipped
                         else "Constructive tape. Run the monthly buy as "
                         "planned — boring is the plan.")}
    if flipped:
        return {"action": "deploy", "tone": "caution", "flipped": True,
                "headline": "Stabilizing — deploy the reserve in tranches.",
                "note": ("Out of defense but not clean yet — deploy half "
                         "the reserve now, rest on confirmation.")}
    return {"action": "split", "tone": "caution",
            "headline": "No edge — split the buy in two.",
            "note": ("Choppy tape. Half now, half in two weeks — "
                     "you lose nothing and buy back flexibility.")}


def _drawdown_ctx(payload: dict, posture: Optional[str],
                  verdict: dict) -> dict:
    fwd = payload.get("forward") or {}
    dc = payload.get("dip_character") or {}
    v200 = payload.get("spy_vs_200")
    b = _bucket(posture)
    if b == "defensive":
        line = ("The tape is broken — that is exactly what a reserve "
                "bucket is for. Pausing buys is not panic; it's the plan "
                "working. Selling the book would be.")
    elif b == "neutral":
        line = ("Pullbacks like this are the price of admission for "
                "equity returns. Nothing about this read says change "
                "the plan — split the buy and keep it boring.")
    else:
        line = ("Constructive tape. The worst move for a passive book "
                "right now is getting cute — buy as planned.")
    return {
        "spy_vs_200": v200,
        "lead_scenario": fwd.get("lead_scenario"),
        "dip_character": dc.get("character"),
        "p_deeper_dip": fwd.get("p_deeper_dip_20d"),
        "verdict_line": line,
    }


def _journal_tilt(as_of, posture: str, matched: str, tilt: dict) -> None:
    """Journal today's suggestion — idempotent per day, graded later."""
    from app.database import db
    try:
        db.execute_update(
            "INSERT INTO passive_tilts (as_of, posture, matched, tilt,"
            " reason) VALUES (:d,:p,:m,CAST(:t AS jsonb),:r)"
            " ON CONFLICT (as_of) DO NOTHING",
            {"d": as_of, "p": posture, "m": matched,
             "t": json.dumps(tilt["w"]), "r": tilt["reason"]})
    except Exception as exc:
        logger.debug("passive tilt journal failed: %s", exc)


def _book_rows() -> list[dict]:
    try:
        rows = _q("SELECT name, weights, note FROM passive_books"
                  " WHERE active ORDER BY id LIMIT 1")
        return rows
    except Exception:
        return []


def _seed_book() -> None:
    from app.database import db
    db.execute_update(
        "INSERT INTO passive_books (name, weights, note)"
        " VALUES (:n, CAST(:w AS jsonb), :note)",
        {"n": BOOK_NAME, "w": json.dumps(BASE_WEIGHTS), "note": BOOK_NOTE})


def payload() -> dict:
    from datetime import date
    # latest regime snapshot → posture
    row = _q("SELECT as_of, stance, payload FROM regime_snapshots"
             " ORDER BY as_of DESC LIMIT 1")
    payload_row = (row[0] if row else {}).get("payload") or {}
    if isinstance(payload_row, str):
        try:
            payload_row = json.loads(payload_row)
        except Exception:
            payload_row = {}

    from app.signals import posture as _posture
    cur = _posture.current()          # journals today's eval too
    posture_name = cur.get("posture")
    matched = cur.get("matched")
    # regime just flipped out of defense? read the journaled evals
    prev_posture = None
    try:
        ev = _q("SELECT posture FROM posture_evals"
                " ORDER BY as_of DESC LIMIT 1 OFFSET 1")
        prev_posture = ev[0]["posture"] if ev else None
    except Exception:
        pass

    verdict = _verdict(posture_name, cur.get("new_longs"), prev_posture)

    book_rows = _book_rows()
    if not book_rows:
        try:
            _seed_book()
            book_rows = _book_rows()
        except Exception:
            pass
    book = book_rows[0] if book_rows else {
        "name": BOOK_NAME, "weights": BASE_WEIGHTS, "note": BOOK_NOTE}
    base_w = book.get("weights") or BASE_WEIGHTS
    if isinstance(base_w, str):
        try:
            base_w = json.loads(base_w)
        except Exception:
            base_w = BASE_WEIGHTS

    tilt = _TILTS[_bucket(posture_name)]
    _journal_tilt(date.today(), posture_name or "neutral",
                  matched or "", tilt)

    try:
        hist = _q("SELECT as_of, posture, tilt, reason FROM passive_tilts"
                  " ORDER BY as_of DESC LIMIT 12")
        for h in hist:
            h["as_of"] = str(h.get("as_of") or "")[:10]
    except Exception:
        hist = []          # table lands with migration 013

    return {
        "as_of": str((row[0] if row else {}).get("as_of") or ""),
        "posture": posture_name, "matched": matched,
        "new_longs": cur.get("new_longs"),
        "verdict": verdict,
        "book": {"name": book.get("name"), "base": base_w,
                 "tilt": tilt["w"], "reason": tilt["reason"],
                 "note": book.get("note")},
        "context": _drawdown_ctx(payload_row, posture_name, verdict),
        "tilt_history": hist,
    }
