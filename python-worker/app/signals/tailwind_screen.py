"""Tailwind candidates — the "early CAT" screen.

Deterministic composition of already-journaled signals; no LLM, no new
scoring engine. A candidate is a name whose economics are beginning to
reprice upward (estimate revisions + revenue acceleration) while the
stock hasn't yet (price return < revision) and it isn't already tagged
as a pure member of a known structural theme — i.e. the market hasn't
filed it under the theme yet. Growth-quality tailwind evidence is a
bonus, not a requirement (coverage is the AI-infra subset only).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MIN_REVISION = 0.05        # analysts chasing: est revision > +5%
_LOOKBACK_DAYS = 63         # ~3m price return for the reprice check
_MAX_FV_GAP = 2.0           # >200% "upside" is a broken model output,
                            # not evidence of cheapness


def _theme_membership() -> dict[str, dict[str, Any]]:
    """symbol → {themes: [...], pure: bool} across active themes."""
    from app.database import db
    rows = db.execute_query(
        "SELECT theme_key, name, members FROM theme_registry "
        "WHERE status='active'")
    out: dict[str, dict[str, Any]] = {}
    for r in rows or []:
        members = r.get("members") or {}
        if isinstance(members, str):
            import json
            members = json.loads(members)
        for sym, tier in members.items():
            e = out.setdefault(sym, {"themes": [], "pure": False})
            e["themes"].append(r["theme_key"])
            if tier == "pure":
                e["pure"] = True
    return out


def run() -> dict[str, Any]:
    from app.database import db
    members = _theme_membership()
    rows = db.execute_query(
        f"""SELECT f.symbol, f.rev_growth, f.rev_accel,
                   f.est_revision_pct, f.fwd_pe, f.gap_score,
                   px.close AS price, px63.close AS price_63d,
                   fv.expected_fair_value,
                   gq.score AS gq_score,
                   gq.tailwinds AS gq_tailwinds,
                   s.momentum_state,
                   COALESCE(s.sector, cp.sector) AS sector
        FROM symbol_flywheel f
        LEFT JOIN LATERAL (
            SELECT close FROM daily_bars b
            WHERE b.symbol = f.symbol
            ORDER BY b.date DESC LIMIT 1) px ON true
        LEFT JOIN LATERAL (
            SELECT close FROM daily_bars b
            WHERE b.symbol = f.symbol
            ORDER BY b.date DESC
            OFFSET {_LOOKBACK_DAYS} LIMIT 1) px63 ON true
        LEFT JOIN LATERAL (
            SELECT expected_fair_value FROM fair_value_v2_runs v
            WHERE v.symbol = f.symbol
            ORDER BY v.as_of DESC, v.run_id DESC LIMIT 1) fv ON true
        LEFT JOIN LATERAL (
            SELECT score,
                   (detail->>'tailwinds')::int AS tailwinds
            FROM growth_quality_runs g
            WHERE g.symbol = f.symbol
            ORDER BY g.as_of DESC, g.id DESC LIMIT 1) gq ON true
        LEFT JOIN stocks s ON s.symbol = f.symbol
        LEFT JOIN fmp_company_profiles cp ON cp.symbol = f.symbol
        ORDER BY f.symbol""")
    # latest weekly LLM attribution per symbol (journal-only layer —
    # it annotates the flags, never alters them)
    try:
        rev_rows = db.execute_query(
            "SELECT DISTINCT ON (symbol) symbol, linkage, confidence,"
            " theme, rationale, as_of FROM tailwind_reviews "
            "ORDER BY symbol, as_of DESC")
        reviews = {r["symbol"]: r for r in rev_rows or []}
    except Exception:
        reviews = {}
    out = []
    for r in rows or []:
        sym = r["symbol"]
        price_ret = None
        if r["price"] and r["price_63d"]:
            price_ret = r["price"] / r["price_63d"] - 1
        fv_gap = None
        if r["expected_fair_value"] and r["price"]:
            fv_gap = r["expected_fair_value"] / r["price"] - 1
        mem = members.get(sym) or {}
        fv_outlier = fv_gap is not None and fv_gap > _MAX_FV_GAP
        # the AI-coverage universe (growth-quality runs) + pure theme
        # members are the "already filed" set — a discovery is a
        # candidate outside it; inside it a pass is confirmation
        known_ai = r["gq_score"] is not None or mem.get("pure", False)
        flags = {
            "accelerating": (r["rev_accel"] or 0) > 0,
            "revisions_up": (r["est_revision_pct"] or 0)
                            > _MIN_REVISION,
            "unrepriced": (price_ret is not None
                           and r["est_revision_pct"] is not None
                           and price_ret < r["est_revision_pct"]),
            "below_fv": (fv_gap is not None
                         and 0 < fv_gap <= _MAX_FV_GAP),
            "not_obvious": not mem.get("pure"),
        }
        core = [flags[k] for k in
                ("accelerating", "revisions_up", "unrepriced",
                 "below_fv", "not_obvious")]
        candidate = all(core)
        discovery = candidate and not known_ai
        evidence = (r["gq_tailwinds"] or 0) > 0
        met = sum(1 for k, v in flags.items() if v) + (1 if evidence
                                                     else 0)
        why = []
        why.append(f"rev accel {'+' if flags['accelerating'] else '≤0'}")
        why.append(f"revisions {r['est_revision_pct']:+.0%}"
                   if r["est_revision_pct"] is not None
                   else "revisions n/a")
        why.append(f"3m price {price_ret:+.0%}"
                   if price_ret is not None else "3m price n/a")
        why.append(f"FV gap {fv_gap:+.0%}"
                   if fv_gap is not None else "FV n/a")
        if fv_outlier:
            why.append("FV outlier — model output suspect")
        elif fv_gap is not None and fv_gap < -0.75:
            why.append("FV premium >75% — model may be blind on "
                       "distorted inputs")
        if mem.get("pure"):
            why.append("known theme member")
        elif mem.get("themes"):
            why.append("theme-adjacent")
        if evidence:
            why.append(f"tailwind evidence ×{r['gq_tailwinds']}")
        rev = reviews.get(sym) or {}
        out.append({
            "symbol": sym,
            "candidate": candidate,
            "discovery": discovery,
            "known_ai": known_ai,
            "fv_outlier": fv_outlier,
            "flags_met": met,
            "flags": flags,
            "tailwind_evidence": evidence,
            "rev_accel": r["rev_accel"],
            "est_revision_pct": r["est_revision_pct"],
            "price_ret_63d": price_ret,
            "fv_gap": fv_gap,
            "fwd_pe": r["fwd_pe"],
            "gap_score": r["gap_score"],
            "gq_score": r["gq_score"],
            "momentum_state": r["momentum_state"],
            "sector": r["sector"],
            "themes": mem.get("themes") or [],
            "why": " · ".join(why),
            "linkage": rev.get("linkage"),
            "linkage_conf": rev.get("confidence"),
            "linkage_theme": rev.get("theme"),
            "linkage_rationale": rev.get("rationale"),
            "linkage_as_of": (str(rev["as_of"])
                              if rev.get("as_of") else None),
        })
    out.sort(key=lambda x: (not x["candidate"], -x["flags_met"],
                            -(x["est_revision_pct"] or 0)))
    cands = [x for x in out if x["candidate"]]
    discoveries = [x for x in cands if x["discovery"]]
    confirmations = [x for x in cands if not x["discovery"]]
    logger.info("tailwind screen: %d discoveries + %d confirmations "
                "/ %d scanned",
                len(discoveries), len(confirmations), len(out))
    return {"candidates": cands, "discoveries": discoveries,
            "confirmations": confirmations, "scanned": len(out),
            "thresholds": {"min_revision": _MIN_REVISION,
                           "lookback_days": _LOOKBACK_DAYS,
                           "max_fv_gap": _MAX_FV_GAP},
            "rows": out}
