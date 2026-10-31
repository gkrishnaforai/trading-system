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

from app.research import (challenge, commitments, design_wins,
                          fdce, news_scan, observations, policy,
                          relationships,
                          products, quarter, scores, sectors)

logger = logging.getLogger(__name__)

# scores jsonb keys — historical names preserved for the frontend;
# new spec names serialize under their own name
_SCORE_KEY = {"ai_tailwind": "tailwind",
              "business_strength": "strength"}


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
    top1 = ctx.get("top1_pct")
    if top1 is not None and top1 >= 0.35:
        gates.append("customer_concentration")
    return gates


def run(sym: str, sector: Optional[str] = None,
        as_of: Optional[date] = None) -> dict:
    from app.database import db
    sym = sym.upper()
    as_of = as_of or date.today()
    sector = sector or sectors.sector_for_symbol(sym)
    cfg = sectors.load(sector)

    model = sectors.classify_model(sym, sector)
    mcfg = sectors.model_cfg(model, sector)

    # news → claims — sector-declared, bounded. Lands in doc_analyses
    # BEFORE the extractors read claims, so fresh news feeds the same
    # evidence hub as filings/pasted docs. Replay runs (as_of past)
    # skip it — injecting today's headlines into a historical replay
    # would violate point-in-time reproducibility.
    news_stats = None
    nsc = cfg.get("news_scan") or {}
    if nsc.get("enabled") and as_of == date.today():
        try:
            news_stats = news_scan.scan(sym, nsc)
        except Exception as exc:
            logger.info("news scan %s: %s", sym, exc)

    in_fdce = fdce.in_universe(sym)
    qs = quarter.quarters(sym)
    qt = quarter.trends(qs)
    prod = products.map_products(
        sym, sector,
        extra_layers=fdce.all_domain_layers() if in_fdce else None,
        with_importance=in_fdce)
    commits = commitments.review(sym)
    cred = commitments.credibility(commits)

    ctx = scores._ctx(sym, model, qt, prod["counts"], commits,
                      sector)
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

    # sector-declared evidence layers — bounded extraction only
    # where the config asks for it (design wins, segment obs)
    wins = []
    if cfg.get("design_wins") or in_fdce:
        wins, dw_reviewed = design_wins.review(
            sym, cfg.get("label", sector), prod["products"])
        ctx.update(design_wins.stats(wins, reviewed=dw_reviewed))

    # relationship extraction — same claims stream as design_wins
    # (doc_analyses), journaled as reviewer_status='extracted'
    # candidates. Replay runs skip it: a PIT snapshot may only read
    # the ledger as it stood, never mint new edges.
    rel_stats = None
    if in_fdce and as_of == date.today():
        try:
            rel_stats = relationships.extract(
                sym, design_wins._claims(sym))
        except Exception as exc:
            logger.info("relationship extract %s: %s", sym, exc)
    if cfg.get("segment_extraction"):
        observations.review(sym, cfg.get("label", sector))
        rev_ttm = sum(q["revenue"]["value"] for q in qs[:4]
                      if q["revenue"]["value"] is not None) or None
        exp = observations.exposure(
            sym, mcfg.get("exposure_terms") or [],
            total_rev=rev_ttm)
        ctx.update({k: exp[k] for k in
                    ("exposed_rev_growth", "exposed_rev_mix")})
        ctx["exposed_segments"] = exp["exposed_segments"]

    # FDCE — cross-sector layer: domain exposure, ECS, transitions,
    # disruption. Feeds ctx fields the FDCS/valuation/technical
    # yamls consume; journaled wholesale into report['fdce'].
    fdce_block = None
    if in_fdce:
        fdce_block = fdce.build(sym, prod["products"], wins, ctx,
                                as_of=as_of)
        ctx.update(fdce_block["ctx"])
        # FDCE's domain-layer rank fills in for sector modules that
        # don't declare nextgen_layers (fdce-only names like PLTR)
        if not ctx.get("nextgen_stage_rank"):
            ctx["nextgen_stage_rank"] = \
                fdce_block["ctx"]["nextgen_stage_rank_fdce"]

    overrides = (cfg.get("model_weight_overrides", {})
                 .get(model) or {})

    # score list is sector-declared — healthcare: tailwind/strength/
    # quality; ai_infra adds the architecture score
    evals = {}
    for sname in cfg.get("scores") or ("ai_tailwind",
                                       "business_strength",
                                       "quality"):
        ov = overrides if sname == "business_strength" else None
        evals[sname] = scores.evaluate(sym, sname, ctx, ov)
    if in_fdce:
        for sname in ("future_demand_capture",
                      "valuation_opportunity",
                      "technical_entry"):
            evals[sname] = scores.evaluate(sym, sname, ctx)
        if fdce_block is not None:
            fdce_block["adjusted_fdcs"] = fdce.adjusted_fdcs(
                evals["future_demand_capture"]["score"],
                fdce_block["transitions"]["adjusted_delta"])
    tw = evals.get("ai_tailwind") or {}
    bs = evals.get("business_strength") or {}
    ctx["ai_tailwind"], ctx["bstrength"] = \
        tw.get("score"), bs.get("score")
    # evidence coverage — share of component weight that produced a
    # real band evaluation across the EVIDENCE-layer scores only
    # (quality/valuation/technical are financial-data driven and
    # always near-full; including them would mask thin research).
    # Feeds the policy's research_incomplete gate and the journaled
    # evidence_state — missing coverage can never cause an exit.
    _EVIDENCE_SCORES = ("ai_tailwind", "business_strength",
                        "ai_infra_architecture",
                        "future_demand_capture")
    covs = [evals[n]["coverage"] for n in _EVIDENCE_SCORES
            if n in evals and evals[n].get("coverage") is not None]
    ctx["evidence_coverage"] = round(sum(covs) / len(covs), 2) \
        if covs else 0.0
    gates = _hard_gates(ctx, mcfg)
    ctx["hard_gate"] = bool(gates)

    rec = policy.evaluate(ctx)
    evidence_state = ("sufficient" if ctx["evidence_coverage"] >= 0.75
                      else "partial"
                      if ctx["evidence_coverage"] >= 0.5
                      else "incomplete")

    evidence = {"model": model, "ctx": ctx, "quarters": qs,
                "trends": qt, "products": prod["products"],
                "design_wins": wins,
                "commitments": commits, "credibility": cred,
                "scores": evals,
                "gates": gates, "recommendation": rec}
    ch = challenge.run(sym, evidence)
    evidence["challenge"] = ch

    all_missing = sorted({m for e in evals.values()
                          for m in e.get("missing") or []})
    report = {
        "symbol": sym, "sector": sector, "business_model": model,
        "scores": {n: e["score"] for n, e in evals.items()},
        "recommendation": rec,
        "hard_gates": gates,
        "quarters": qs, "trends": qt,
        "products": prod["products"],
        "design_wins": wins,
        "moat_mechanisms": prod["moat_mechanisms"],
        "commitments": commits, "credibility": cred,
        "challenge": ch["findings"],
        "fdce": fdce_block,
        "coverage": {**{n: e["coverage"] for n, e in
                        evals.items()},
                     "missing": all_missing},
        "evidence_coverage": ctx["evidence_coverage"],
        "evidence_state": evidence_state,
        **({"news_scan": news_stats} if news_stats else {}),
        **({"relationship_extract": rel_stats} if rel_stats else {}),
        "rules_version": {"scores": [e["rules_version"]
                                    for e in evals.values()],
                          "policy": rec["rules_version"],
                          **({"domains": fdce.registry_version()}
                             if in_fdce else {})}}
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
             "tw": tw.get("score"), "bs": bs.get("score"),
             "rec": rec["action"],
             "sc": json.dumps(
                 {_SCORE_KEY.get(n, n): e for n, e in
                  evals.items()}, default=str),
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
