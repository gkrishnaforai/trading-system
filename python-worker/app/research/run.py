"""Research orchestrator — one symbol, one journal row.

Sequencing per the spec: evidence first (quarters, products,
commitments), analysis second (scores), decisions last (challenge +
policy + report). Every artifact lands in research_runs — a
point-in-time row, never overwritten, replayable from journaled
inputs.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from app.research import (challenge, commitments, policy, products,
                          quarter, scores, sectors)

logger = logging.getLogger(__name__)


def _hard_gates(ctx: dict, model_cfg: dict) -> list[str]:
    """Sector risk_gates — deterministic evaluation of the ones data
    can decide; the rest stay human-flagged."""
    gates = []
    fcf, runway = ctx.get("fcf_ttm"), ctx.get("runway_quarters")
    if not model_cfg.get("profitability_expected", True):
        if runway is not None and runway < 4:
            gates.append("severe_financing")
    dil = ctx.get("dilution_pct")
    if dil is not None and dil >= 0.15 and (fcf or 0) < 0:
        gates.append("dilution_critical")
    return gates


def run(sym: str, sector: str = "healthcare",
        as_of: Optional[date] = None) -> dict:
    from app.database import db
    sym = sym.upper()
    as_of = as_of or date.today()

    model = sectors.classify_model(sym, sector)
    mcfg = sectors.model_cfg(model, sector)

    qs = quarter.quarters(sym)
    qt = quarter.trends(qs)
    prod = products.map_products(sym, sector)
    commits = commitments.review(sym)
    cred = commitments.credibility(commits)

    ctx = scores._ctx(sym, model, qt, prod["counts"], commits)
    ctx.update({
        "ai_tailwind": None,       # filled post-eval for policy
        "bstrength": None,
        "hard_gate": False,
        "thesis_status": _thesis(sym)})
    # quality dims need trend reads + the commitment record
    ctx.update({k: qt.get(k) for k in
                ("rev_yoy", "rev_qoq", "fcf_conversion",
                 "margin_trend")})
    ctx["commit_tracked"] = cred.get("tracked")
    ctx["commit_negative"] = cred.get("negative")
    overrides = (sectors.load(sector)
                 .get("model_weight_overrides", {}).get(model) or {})

    tw = scores.evaluate(sym, "ai_tailwind", ctx)
    bs = scores.evaluate(sym, "business_strength", ctx, overrides)
    qt_score = scores.evaluate(sym, "quality", ctx)
    ctx["ai_tailwind"], ctx["bstrength"] = tw["score"], bs["score"]
    gates = _hard_gates(ctx, mcfg)
    ctx["hard_gate"] = bool(gates)

    rec = policy.evaluate(ctx)

    evidence = {"model": model, "ctx": ctx, "quarters": qs,
                "trends": qt, "products": prod["products"],
                "commitments": commits, "credibility": cred,
                "scores": {"ai_tailwind": tw,
                           "business_strength": bs,
                           "quality": qt_score},
                "gates": gates, "recommendation": rec}
    ch = challenge.run(sym, evidence)
    evidence["challenge"] = ch

    report = {
        "symbol": sym, "sector": sector, "business_model": model,
        "scores": {"ai_tailwind": tw["score"],
                   "business_strength": bs["score"],
                   "quality": qt_score["score"]},
        "recommendation": rec,
        "hard_gates": gates,
        "quarters": qs, "trends": qt,
        "products": prod["products"],
        "moat_mechanisms": prod["moat_mechanisms"],
        "commitments": commits, "credibility": cred,
        "challenge": ch["findings"],
        "coverage": {"tailwind": tw["coverage"],
                     "strength": bs["coverage"],
                     "quality": qt_score["coverage"],
                     "missing": sorted(set(
                         tw["missing"] + bs["missing"]
                         + qt_score["missing"]))},
        "rules_version": {"scores": [tw["rules_version"],
                                    bs["rules_version"],
                                    qt_score["rules_version"]],
                          "policy": rec["rules_version"]}}
    try:
        db.execute_update(
            "INSERT INTO research_runs (symbol, as_of, sector,"
            " business_model, ai_tailwind_score, business_strength,"
            " recommendation, scores, report, rules_version)"
            " VALUES (:s,:d,:sec,:m,:tw,:bs,:rec,CAST(:sc AS jsonb),"
            " CAST(:rp AS jsonb),:rv)"
            " ON CONFLICT (symbol, as_of) DO UPDATE SET"
            " ai_tailwind_score=EXCLUDED.ai_tailwind_score,"
            " business_strength=EXCLUDED.business_strength,"
            " recommendation=EXCLUDED.recommendation,"
            " scores=EXCLUDED.scores, report=EXCLUDED.report",
            {"s": sym, "d": as_of, "sec": sector, "m": model,
             "tw": tw["score"], "bs": bs["score"],
             "rec": rec["action"],
             "sc": json.dumps({"tailwind": tw, "strength": bs,
                               "quality": qt_score}, default=str),
             "rp": json.dumps(report, default=str),
             "rv": report["rules_version"]["policy"]})
    except Exception as exc:
        logger.warning("research journal %s: %s", sym, exc)
        report["journal_error"] = str(exc)[:120]
    return report


def _thesis(sym: str) -> Optional[str]:
    from app.database import db
    try:
        r = db.execute_query(
            "SELECT status FROM symbol_thesis WHERE symbol=:s",
            {"s": sym.upper()})
        return r[0]["status"] if r else None
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    s = sys.argv[1] if len(sys.argv) > 1 else "ISRG"
    print(json.dumps(run(s), indent=2, default=str))
