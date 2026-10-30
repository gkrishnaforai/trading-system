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
         product_counts: dict, commit_rows: list,
         sector: str = "healthcare") -> dict:
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
            "SELECT emerging_growth, momentum_state FROM stocks"
            " WHERE symbol=:s",
            {"s": sym})
        c["emerging_growth"] = bool(r[0]["emerging_growth"]) \
            if r and r[0]["emerging_growth"] is not None else None
        c["momentum_state"] = r[0].get("momentum_state") \
            if r else None
    except Exception:
        c["emerging_growth"] = None
        c["momentum_state"] = None
    try:
        r = db.execute_query(
            "SELECT top1_pct FROM symbol_customer_conc"
            " WHERE symbol=:s", {"s": sym})
        c["top1_pct"] = _f(r[0]["top1_pct"]) if r else None
    except Exception:
        c["top1_pct"] = None
    # sector opportunity tag — classified model with a mapped
    # opportunity space
    from app.research import sectors
    c["opportunity_tagged"] = bool(
        sectors.model_cfg(model, sector).get("opportunities")) \
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
    coverage. `name` = ai_tailwind | business_strength | ...

    Evidence contract: a component that cannot be evaluated is
    UNKNOWN — never a silent zero. Bands may declare `unknown:
    true` explicitly (e.g. "no product map" is not "no moat");
    a component whose bands all fail after touching missing inputs
    is unknown too. Unknown components are excluded from the
    weighted total, which renormalizes over the answered weight —
    the score reflects the evidence that exists, and `coverage`
    (answered-weight share) says how much of the spec that was."""
    spec = _spec(name)
    weights = _weights(spec, overrides or {})
    missing: list = []
    comps = {}
    for comp, cfg in (spec.get("components") or {}).items():
        sc, note, unk = None, None, False
        n_missing_before = len(missing)
        for band in cfg.get("bands") or []:
            if "default" in band:
                sc, note = band["default"], band.get("note")
                continue
            if _cond(ctx, band.get("if") or {}, missing, {}):
                if band.get("unknown"):
                    # explicit unknown beats any default applied
                    # earlier in the list
                    sc, note, unk = None, band.get("note"), True
                else:
                    sc, note = band["score"], band.get("note")
                break
        if sc is None and not unk:
            unk = True
            note = ("insufficient evidence: "
                    + ",".join(sorted(set(
                        missing[n_missing_before:]))[:4])
                    if len(missing) > n_missing_before
                    else "no band matched")
        comps[comp] = {"score": sc, "weight": round(
            weights.get(comp, 0), 1), "note": note,
            **({"unknown": True} if unk else {})}
    answered_w = sum(c["weight"] for c in comps.values()
                     if not c.get("unknown"))
    total_w = sum(c["weight"] for c in comps.values())
    total = (sum(c["score"] * c["weight"]
                 for c in comps.values() if not c.get("unknown"))
             / answered_w if answered_w > 0 else None)
    # caps — semantic limits no component sum can override. E.g. a
    # company with no AI linkage can't post a high *tailwind* score
    # just because its moat is strong; the cap is journaled.
    capped = None
    from app.signals.pulse_engine import _eval_when
    for cap in spec.get("caps") or []:
        matched, _log = _eval_when(ctx, cap.get("when") or {}, {})
        missing.extend(_log.get("missing") or [])
        if matched and total is not None and total > cap["cap"]:
            total, capped = cap["cap"], cap.get("note")
            break
    return {"score": round(total, 1) if total is not None else None,
            "components": comps,
            "capped": capped,
            "missing": sorted(set(missing)),
            "unknown_components": sorted(
                k for k, c in comps.items() if c.get("unknown")),
            "coverage": round(answered_w / total_w, 2)
            if total_w else None,
            "rules_version": f"{name}@{spec.get('version', 0)}"}
