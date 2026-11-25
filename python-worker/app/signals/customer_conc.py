"""Customer concentration — level AND drift.

The reviewer's ask isn't 'is the company concentrated' — it's 'is it
BECOMING more dependent on one or two customers'. Level lives in
symbol_customer_conc (manually curated; XBRL has no customer-share
tag — the data is in 10-K text). Drift needs history, so every read
journals an observation to symbol_customer_conc_hist when the value
changes or ≥30d has passed; drift = latest vs prior observation.

Reads stay honest: no history = drift None, flag absent — never a
fabricated 'stable'.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

_OBS_GAP_D = 30          # re-journal at most monthly if unchanged
_RISE_PP = 0.05          # +5pp top-1 share = 'conc_rising'


def customer_conc(sym: str, *, note: bool = False) -> dict[str, Any]:
    """{top1_pct, drift_pp, flag, obs_n, top5_note?} — drift_pp is the
    change vs the prior journaled observation of the same curated
    field; obs_n discloses how much history the drift stands on."""
    from app.database import db
    out: dict[str, Any] = {"top1_pct": None, "drift_pp": None,
                           "flag": None, "obs_n": 0}
    sym = sym.upper()
    try:
        r = db.execute_query(
            "SELECT top1_pct, top5_note FROM symbol_customer_conc"
            " WHERE symbol=:s", {"s": sym})
        if not r:
            return out
        top1 = r[0]["top1_pct"]
        if top1 is not None:
            top1 = float(top1)
        out["top1_pct"] = top1
        if note:
            out["top5_note"] = r[0]["top5_note"]
    except Exception as exc:
        logger.debug("cust_conc read %s: %s", sym, exc)
        return out
    # observe — journal the curated level so drift accrues over time
    try:
        prev = db.execute_query(
            "SELECT as_of, top1_pct FROM symbol_customer_conc_hist"
            " WHERE symbol=:s ORDER BY as_of DESC LIMIT 2",
            {"s": sym})
        latest = prev[0] if prev else None
        due = (latest is None
               or (top1 is not None
                   and latest["top1_pct"] is not None
                   and abs(top1 - float(latest["top1_pct"])) > 1e-9)
               or (date.today() - latest["as_of"]).days >= _OBS_GAP_D)
        if due and top1 is not None:
            db.execute_update(
                "INSERT INTO symbol_customer_conc_hist"
                " (symbol, as_of, top1_pct)"
                " VALUES (:s,:d,:p)"
                " ON CONFLICT (symbol, as_of) DO UPDATE SET"
                " top1_pct=EXCLUDED.top1_pct",
                {"s": sym, "d": date.today(), "p": top1})
            prev = db.execute_query(
                "SELECT as_of, top1_pct FROM symbol_customer_conc_hist"
                " WHERE symbol=:s ORDER BY as_of DESC LIMIT 2",
                {"s": sym})
        out["obs_n"] = len(prev)
        if len(prev) >= 2 and top1 is not None \
                and prev[1]["top1_pct"] is not None:
            out["drift_pp"] = round(top1 - float(prev[1]["top1_pct"]), 4)
            if out["drift_pp"] >= _RISE_PP:
                out["flag"] = "conc_rising"
            elif out["drift_pp"] <= -_RISE_PP:
                out["flag"] = "conc_easing"
            else:
                out["flag"] = "stable"
    except Exception as exc:
        logger.debug("cust_conc hist %s: %s", sym, exc)
    return out
