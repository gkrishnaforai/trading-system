"""Run-vs-run delta — what the latest research pass actually changed.

A bare score on the page can't answer 'is there new research and
what did it do'. This diffs two journaled research_runs rows into a
small honest summary: score moves, evidence that landed (products,
design wins, news articles analyzed), and recommendation changes.
Pure function — the API composes it.
"""
from __future__ import annotations

from typing import Any

_SCORE_KEYS = ("tailwind", "strength", "quality",
               "ai_infra_architecture", "future_demand_capture",
               "valuation_opportunity", "technical_entry")


def _names(rows: list[dict] | None, key: str) -> set[str]:
    return {str(r.get(key) or "").strip().lower()
            for r in rows or [] if r.get(key)}


def compute(cur: dict, prev: dict | None) -> dict[str, Any]:
    """cur/prev: parsed research_runs rows (scores + report dicts).
    {} when there's no prior run — a first run has nothing to
    diff against, and rendering 'new' for everything would lie."""
    if not prev:
        return {}
    cs, ps = cur.get("scores") or {}, prev.get("scores") or {}
    diffs = {}
    for k in _SCORE_KEYS:
        c = (cs.get(k) or {}).get("score")
        p = (ps.get(k) or {}).get("score")
        if isinstance(c, (int, float)) and isinstance(p, (int, float)) \
                and c != p:
            diffs[k] = round(c - p, 1)

    cr, pr = cur.get("report") or {}, prev.get("report") or {}
    prev_prod = _names(pr.get("products"), "name")
    prev_win = _names(pr.get("design_wins"), "customer")
    new_products = [str(p.get("name")) for p in (cr.get("products") or [])
                    if p.get("name") and
                    str(p["name"]).strip().lower() not in prev_prod]
    new_wins = [str(w.get("customer"))
                for w in (cr.get("design_wins") or [])
                if w.get("customer") and
                str(w["customer"]).strip().lower() not in prev_win]

    def _rec(rep):
        r = rep.get("recommendation")
        return r if isinstance(r, dict) else {}
    rc_cur, rc_prev = _rec(cr), _rec(pr)
    rec_change = None
    if rc_cur.get("action") and rc_prev.get("action") \
            and rc_cur["action"] != rc_prev["action"]:
        rec_change = {"from": rc_prev["action"],
                      "to": rc_cur["action"]}

    return {"prev_as_of": str(prev.get("as_of") or ""),
            "score_diffs": diffs,
            "new_products": new_products,
            "new_wins": new_wins,
            "rec_change": rec_change,
            "news_scan": cr.get("news_scan") or None}
