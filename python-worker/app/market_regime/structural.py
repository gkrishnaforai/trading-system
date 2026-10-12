"""Structural read-layer — the slow-cadence regime monitors.

The daily engine (state→facts→rules) answers "what is the market doing
today". This module answers "what is changing underneath it" by reading
the JOURNALS of the three slow monitors — it recomputes nothing:

    capex_snapshots     capex_cycle engine — 7-leg AI-capex slowdown
                        score, band, guidance (runs with momentum job)
    macro_snapshots     FRED module scores — growth/labor/inflation/
                        rates/credit/liquidity/housing/manufacturing
                        (fred-macro job; empty until a key lands)
    transcript_scores   SEC 8-K language — demand/capex/orders drift

Output contract: every block carries as_of + staleness so a stale
quarter never masquerades as signal. Regime relevance stays where it
belongs — facts.py reads this as drivers + confirmation keys, NOT
score weights, until the journals are long enough to calibrate.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# capex band → the proposal's alert hierarchy (watch/prepare/act/
# confirmed) — mapped, not re-scored
_ALERT = {
    "expansion": None,
    "normalization": "watch",
    "slowing": "prepare",
    "serious_slowdown": "act",
    "contraction": "confirmed",
}


def _age(as_of: Optional[str]) -> Optional[int]:
    try:
        return (date.today() - date.fromisoformat(str(as_of)[:10])).days
    except Exception:
        return None


def read() -> dict[str, Any]:
    """Latest structural state — one DB hit per journal, always fast.
    Returns {} on any failure — structural context must never break
    the regime card."""
    out: dict[str, Any] = {}
    try:
        from app.database import db

        cx = db.execute_query(
            "SELECT as_of, score, components FROM capex_snapshots "
            "ORDER BY as_of DESC LIMIT 1")
        if cx:
            row = cx[0]
            try:
                from app.signals import capex_cycle
                payload = capex_cycle.read() or {}
            except Exception:
                payload = {}
            band = payload.get("band")
            out["capex"] = {
                "score": float(row["score"]) if row["score"] else None,
                "band": band,
                "alert": _ALERT.get(band or ""),
                "flags": payload.get("flags") or [],
                "d3m": payload.get("d3m"),
                "d6m": payload.get("d6m"),
                "n_elevated": payload.get("n_elevated"),
                "components": row.get("components") or {},
                "guidance": (payload.get("guidance") or {}).get("meaning"),
                "as_of": str(row["as_of"]),
                "age_days": _age(row["as_of"]),
            }

        ms = db.execute_query(
            "SELECT as_of_date, module_scores, overall_score, "
            "regime_probs FROM macro_snapshots "
            "ORDER BY as_of_date DESC LIMIT 1")
        if ms:
            row = ms[0]
            out["macro"] = {
                "overall": (float(row["overall_score"])
                            if row["overall_score"] is not None else None),
                "modules": row.get("module_scores") or {},
                "regime_probs": row.get("regime_probs") or {},
                "as_of": str(row["as_of_date"]),
                "age_days": _age(row["as_of_date"]),
            }

        ts = db.execute_query(
            "SELECT symbol, doc_period, role, demand_score, "
            "capex_dir, orders_language, confidence "
            "FROM transcript_scores "
            "ORDER BY doc_period DESC LIMIT 40")
        if ts:
            out["language"] = {
                "scored_quarters": len(ts),
                "latest_period": ts[0].get("doc_period"),
                "as_of": ts[0].get("doc_period"),
            }
    except Exception as exc:
        logger.debug("structural read failed: %s", exc)
    return out


def changes(prev: Optional[dict], cur: dict) -> list[str]:
    """'What changed underneath' — compare today's structural block
    with yesterday's journaled one. Plain-English lines for the
    morning card; None-safe, missing data simply produces no line."""
    if not isinstance(prev, dict) or not cur:
        return []
    out: list[str] = []
    pc, cc = prev.get("capex") or {}, cur.get("capex") or {}
    if cc.get("band") and pc.get("band") and cc["band"] != pc["band"]:
        out.append(f"capex regime moved {pc['band']} → {cc['band']}")
    if (cc.get("score") is not None and pc.get("score") is not None
            and abs(cc["score"] - pc["score"]) >= 3):
        out.append(f"capex score {pc['score']:.0f} → {cc['score']:.0f}")
    pm, cm = prev.get("macro") or {}, cur.get("macro") or {}
    pmods, cmods = pm.get("modules") or {}, cm.get("modules") or {}
    for mod, cv in cmods.items():
        pv = (pmods.get(mod) or {}).get("score")
        cv = cv.get("score") if isinstance(cv, dict) else cv
        try:
            if pv is not None and cv is not None \
                    and abs(float(cv) - float(pv)) >= 8:
                out.append(f"FRED {mod} {float(pv):.0f} → "
                           f"{float(cv):.0f}")
        except (TypeError, ValueError):
            continue
    return out
