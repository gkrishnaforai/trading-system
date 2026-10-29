"""Research scorer — versioned, journaled, deterministic.

Two yaml-weighted scores evaluated by the SAME _cond engine as
pulse_action_rules/best_picks — no second condition language.
Each component: ordered bands, first match wins; a missing input
fails the band and lands in the missing log (never vacuous-true,
never silently zero). Model weight overrides come from the sector
config and renormalize — early-stage models don't eat profitability
penalties they can't satisfy.

The LLM never assigns or overrides scores. Whatever it narrates is
advisory prose on top of journaled numbers.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from app.signals.pulse_engine import _cond

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / "scores"


@lru_cache(maxsize=8)
def _spec(name: str) -> dict:
    return yaml.safe_load((_DIR / f"{name}.yaml").read_text())


def _f(v) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _ctx(sym: str, model: str, quarter_trends: dict,
         product_counts: dict, commit_rows: list) -> dict:
    """Assemble the scoring context from journaled signals —
    every field traces to a stored row."""
    from app.database import db
    sym = sym.upper()
    c: dict[str, Any] = {"model": model}
    try:
        r = db.execute_query(
            "SELECT rev_growth, rev_accel, est_revision_pct, fwd_pe,"
            " gap_score, roic, fcf_ttm, fcf_margin, om_now,"
            " net_debt_ebitda FROM symbol_flywheel WHERE symbol=:s",
            {"s": sym})
        if r:
            c.update({k: _f(r[0].get(k)) for k in
                      ("rev_growth", "rev_accel", "est_revision_pct",
                       "fwd_pe", "gap_score", "roic", "fcf_ttm",
                       "fcf_margin", "om_now")})
            c["nde"] = _f(r[0].get("net_debt_ebitda"))
    except Exception as exc:
        logger.debug("research ctx flywheel %s: %s", sym, exc)
    try:
        r = db.execute_query(
            "SELECT linkage FROM tailwind_reviews WHERE symbol=:s"
            " ORDER BY as_of DESC LIMIT 1", {"s": sym})
        c["ai_linkage"] = r[0]["linkage"] if r else None
    except Exception:
        c["ai_linkage"] = None
    try:
        r = db.execute_query(
            "SELECT score FROM growth_quality_runs WHERE symbol=:s"
            " ORDER BY as_of DESC, id DESC LIMIT 1", {"s": sym})
        c["gq_score"] = _f(r[0]["score"]) if r else None
    except Exception:
        c["gq_score"] = None
    try:
        r = db.execute_query(
            "SELECT emerging_growth FROM stocks WHERE symbol=:s",
            {"s": sym})
        c["emerging_growth"] = bool(r[0]["emerging_growth"]) \
            if r and r[0]["emerging_growth"] is not None else None
    except Exception:
        c["emerging_growth"] = None
    # sector opportunity tag — classified model with a mapped
    # opportunity space
    from app.research import sectors
    c["opportunity_tagged"] = bool(
        sectors.model_cfg(model).get("opportunities")) \
        if model != "unclassified" else False
    # product + driver evidence counts
    c.update(product_counts)
    raises = sum(1 for r in commit_rows
                 if r.get("delta_dir") == "raised")
    cuts = sum(1 for r in commit_rows
               if r.get("delta_dir") == "cut")
    c["driver_raises"] = raises
    c["driver_cuts"] = cuts
    # quarter-derived fields
    c["dilution_pct"] = quarter_trends.get("dilution_yoy")
    c["runway_quarters"] = quarter_trends.get("runway_quarters")
    return c


def _weights(spec: dict, overrides: dict) -> dict[str, float]:
    """Model overrides renormalize — a 0-weight component's share
    spreads pro-rata across the rest, never silently drops."""
    w = {k: float(v.get("weight", 0)) for k, v in
         (spec.get("components") or {}).items()}
    for k, ov in (overrides or {}).items():
        if k in w:
            w[k] = float(ov)
    total = sum(v for v in w.values() if v > 0)
    return {k: (v / total * 100 if total else 0) for k, v in
            w.items()}


def evaluate(sym: str, name: str, ctx: dict,
             overrides: Optional[dict] = None) -> dict:
    """One score spec → component breakdown + weighted total +
    confidence. `name` = ai_tailwind | business_strength."""
    spec = _spec(name)
    weights = _weights(spec, overrides or {})
    missing: list = []
    comps = {}
    for comp, cfg in (spec.get("components") or {}).items():
        sc, note = None, None
        for band in cfg.get("bands") or []:
            if "default" in band:
                sc, note = band["default"], band.get("note")
                continue
            if _cond(ctx, band.get("if") or {}, missing, {}):
                sc, note = band["score"], band.get("note")
                break
        if sc is None:
            sc, note = 0, "no band matched"
        comps[comp] = {"score": sc, "weight": round(
            weights.get(comp, 0), 1), "note": note}
    total = sum(c["score"] * c["weight"] / 100
                for c in comps.values())
    # caps — semantic limits no component sum can override. E.g. a
    # company with no AI linkage can't post a high *tailwind* score
    # just because its moat is strong; the cap is journaled.
    capped = None
    from app.signals.pulse_engine import _eval_when
    for cap in spec.get("caps") or []:
        matched, _log = _eval_when(ctx, cap.get("when") or {}, {})
        missing.extend(_log.get("missing") or [])
        if matched and total > cap["cap"]:
            total, capped = cap["cap"], cap.get("note")
            break
    # coverage = share of weighted components whose band evaluation
    # touched no missing inputs — approximated by missing count vs
    # ctx fields used. Simple and auditable.
    n_missing = len(set(missing))
    coverage = max(0.0, 1.0 - 0.1 * n_missing)
    return {"score": round(total, 1),
            "components": comps,
            "capped": capped,
            "missing": sorted(set(missing)),
            "coverage": round(coverage, 2),
            "rules_version": f"{name}@{spec.get('version', 0)}"}
