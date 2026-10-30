"""Future Demand Capture Engine (FDCE) — cross-sector layer.

Answers: what will become bottlenecked → who can supply it → who
captures the economics. Three separations the spec insists on:
  Need (domain demand D_d) vs Capability (company's products) vs
  Capture (FDCS). Domain heat never inflates a weak supplier.

Exposure is WEIGHTED — a product's weight is its disclosed revenue
share when available, else its evidence-grounded strategic
importance. Both are never inferred; an ungrounded product simply
carries low weight. ECS is the same weighted aggregation over the
E0-E5 evidence ladder plus retained exposure breakdowns.

Deterministic throughout: the LLM classified products upstream;
this module only does set-membership + arithmetic. Everything is
journaled into research_runs.report['fdce'] with the domains
registry version for PIT replay.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_PATH = Path(__file__).parent / "domains.yaml"

# product stage → spec evidence ladder
# E5 revenue-producing · E4 ramp/orders/backlog · E3 qualified win ·
# E2 announced partnership/prototype · E1 roadmap · E0 speculative
_E_STAGE = {"revenue": 5, "rollout": 4, "partnership": 3,
            "pipeline": 2, "aspiration": 1}
_E_WIN = {"scaling": 5, "production": 4, "qualification": 3,
          "sampling": 2, "announced": 2}
_E_LABEL = {5: "E5 revenue-producing", 4: "E4 production ramp",
            3: "E3 qualified design win", 2: "E2 announced/pilot",
            1: "E1 roadmap", 0: "E0 speculative"}

# moat mechanisms that mean a product is hard to bypass/replicate
_BOTTLENECK_MECHS = {"design_win_lock", "hyperscaler_qualification",
                     "capacity_reservation", "process_technology",
                     "regulatory_moat"}
_REPLICATION_MECHS = _BOTTLENECK_MECHS | {
    "ip_patents", "ecosystem_lockin", "installed_base"}


@lru_cache(maxsize=4)
def load() -> dict[str, Any]:
    return yaml.safe_load(_PATH.read_text())


def registry_version() -> str:
    return f"domains@{load().get('version', 0)}"


def universe() -> dict[str, dict]:
    return load().get("universe") or {}


def in_universe(sym: str) -> bool:
    return sym.upper() in universe()


def domain_cfg(domain: str) -> dict:
    return (load().get("domains") or {}).get(domain, {})


def layer_domain_map() -> dict[str, str]:
    """layer → domain (first declaring domain wins on collision)."""
    out = {}
    for d, cfg in (load().get("domains") or {}).items():
        for lay in cfg.get("layers") or []:
            out.setdefault(lay, d)
    return out


def all_domain_layers() -> list[str]:
    return sorted(layer_domain_map().keys())


def _d_score(domain: str) -> Optional[float]:
    """D_d = .30G+.25B+.20A+.15T+.10S — domain opportunity seeds."""
    d = (domain_cfg(domain).get("d") or {})
    if not d:
        return None
    return (0.30 * d.get("growth", 0) + 0.25 * d.get("bottleneck", 0)
            + 0.20 * d.get("adoption", 0)
            + 0.15 * d.get("time_to_scale", 0)
            + 0.10 * d.get("strategic", 0))


def _product_weight(p: dict) -> float:
    """Disclosed revenue share when present; else strategic
    importance /100. Never inferred — ungrounded products weigh ~0."""
    for k in ("revenue_share_pct", "revenue_contribution_pct"):
        v = p.get(k)
        if v is None:
            ev = p.get("evidence") or {}
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            v = ev.get(k)
        if v is not None:
            try:
                return min(float(v) / (100 if float(v) > 1 else 1),
                           1.0)
            except (TypeError, ValueError):
                pass
    si = p.get("strategic_importance")
    if si is None:
        ev = p.get("evidence") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        si = ev.get("strategic_importance")
    try:
        return min(float(si) / 100.0, 1.0) if si is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _e_level(p: dict, wins_by_product: dict) -> int:
    """Product evidence level — a matching design win's stage can
    raise it (the win IS the evidence)."""
    e = _E_STAGE.get(p.get("stage") or "", 0)
    key = str(p.get("name") or "").lower()
    for pname, w in wins_by_product.items():
        if pname and (pname in key or key in pname):
            e = max(e, _E_WIN.get(w.get("stage") or "", 0))
    return e


def domain_exposure(products: list[dict],
                    wins_by_product: Optional[dict] = None
                    ) -> dict[str, dict]:
    """Weighted per-domain exposure. Returns {domain: {weight,
    products:[names], best_e, horizon}} — set membership alone is
    never enough; weight decides."""
    lmap = layer_domain_map()
    out: dict[str, dict] = {}
    for p in products:
        lay = p.get("layer")
        if not lay:
            ev = p.get("evidence") or {}
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            lay = ev.get("layer")
        dom = lmap.get(lay or "")
        if not dom:
            continue
        w = _product_weight(p)
        e = _e_level(p, wins_by_product or {})
        d = out.setdefault(dom, {"weight": 0.0, "products": [],
                                 "best_e": 0})
        d["weight"] += w
        d["products"].append(str(p.get("name") or ""))
        d["best_e"] = max(d["best_e"], e)
    for dom, d in out.items():
        d["horizon"] = domain_cfg(dom).get("horizon")
        d["d_score"] = round(_d_score(dom) or 0, 1)
    return out


def demand_score(exposure: dict[str, dict]) -> Optional[float]:
    """Exposure-weighted domain demand — Σ D_d·E_d / Σ E_d. The
    company rides its REAL domains, not the hottest one."""
    num = den = 0.0
    for dom, d in exposure.items():
        w = d.get("weight") or 0
        ds = _d_score(dom)
        if ds is None or w <= 0:
            continue
        num += ds * w
        den += w
    return round(num / den, 1) if den > 0 else None


def ecs(products: list[dict], wins_by_product: Optional[dict] = None
        ) -> dict[str, Any]:
    """Evidence Confidence Score — exposure-weighted E-ladder mean,
    plus the retained breakdowns the spec asks for. An E1 roadmap
    majority cannot hide behind one E5 product."""
    tot_w = num = 0.0
    rev_w = prod_w = road_w = 0.0
    covered = 0
    best_e = 0
    for p in products:
        w = _product_weight(p)
        e = _e_level(p, wins_by_product or {})
        conf = p.get("confidence")
        try:
            conf = float(conf) if conf is not None else 0.5
        except (TypeError, ValueError):
            conf = 0.5
        conf = min(max(conf, 0.0), 1.0)
        if w > 0:
            tot_w += w
            num += w * e * conf
            if e >= 5:
                rev_w += w
            if e >= 4:
                prod_w += w
            if e <= 2:
                road_w += w
        best_e = max(best_e, e)
        if p.get("quote") or not p.get("synthetic", True):
            covered += 1
    n = len(products)
    if tot_w <= 0:
        return {"ecs": None, "highest_evidence_stage": _E_LABEL[best_e],
                "revenue_confirmed_exposure_pct": None,
                "production_exposure_pct": None,
                "roadmap_exposure_pct": None,
                "evidence_coverage_pct": round(covered / n, 2)
                if n else None}
    return {
        "ecs": round(num / tot_w * 20, 1),          # E5 → 100
        "highest_evidence_stage": _E_LABEL[best_e],
        "revenue_confirmed_exposure_pct": round(rev_w / tot_w, 3),
        "production_exposure_pct": round(prod_w / tot_w, 3),
        "roadmap_exposure_pct": round(road_w / tot_w, 3),
        "evidence_coverage_pct": round(covered / n, 2) if n else None}


_T_CLASS = {"gains_direct": "direct_beneficiary",
            "gains_indirect": "indirect_beneficiary",
            "loses_at_risk": "at_risk",
            "loses_displaced": "displaced"}
_T_DELTA = {"direct_beneficiary": 5, "indirect_beneficiary": 2,
            "at_risk": -4, "displaced": -10}


def transition_exposure(products: list[dict]) -> dict[str, Any]:
    """Product-LEVEL classification per registry transition — a
    company may be beneficiary AND at-risk across its book."""
    hits = []
    for p in products:
        lay = p.get("layer")
        if not lay:
            ev = p.get("evidence") or {}
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            lay = ev.get("layer")
        if not lay:
            continue
        for t in load().get("transitions") or []:
            for field, cls in _T_CLASS.items():
                if lay in (t.get(field) or []):
                    hits.append({
                        "transition": t["id"], "label": t["label"],
                        "product": p.get("name"), "layer": lay,
                        "classification": cls,
                        "confidence": t.get("confidence", 0.5)})
    pos = sum(1 for h in hits if h["classification"]
              in ("direct_beneficiary", "indirect_beneficiary"))
    neg = len(hits) - pos
    delta = sum(_T_DELTA[h["classification"]] * h["confidence"]
                for h in hits)
    if pos and neg:
        net = "mixed"
    elif pos:
        net = "positive"
    elif neg:
        net = "negative"
    else:
        net = "uncertain"
    return {"items": hits, "net": net,
            "adjusted_delta": round(delta, 1)}


def disruption(products: list[dict], mechs: set, top1: Optional[float],
               trans: dict) -> dict[str, Any]:
    """Replication/displacement assessment — deterministic
    heuristics journaled as assessment, never as fact."""
    layers = {p.get("layer") for p in products}
    if None in layers:
        layers.discard(None)
    mechs = set(mechs or ())
    rep = len(mechs & _REPLICATION_MECHS)
    sw_layers = {"orchestration", "workflow_exec", "observability",
                 "inference_platform", "ai_security",
                 "data_governance"}
    loses = {h["layer"] for h in trans.get("items") or []
             if h["classification"] in ("at_risk", "displaced")}
    return {
        "replication_difficulty": (
            "high" if rep >= 2 else "medium" if rep >= 1
            else "low"),
        "hyperscaler_internalization_risk": (
            "elevated" if not mechs & {"design_win_lock",
                                       "hyperscaler_qualification"}
            else "low"),
        "open_source_commoditization_risk": (
            "elevated" if layers & sw_layers
            and not mechs & {"ecosystem_lockin", "ip_patents"}
            else None),
        "architecture_substitution_risk": (
            "elevated: " + ",".join(sorted(loses)) if loses
            else None),
        "customer_concentration_risk": (
            "high" if (top1 or 0) >= 0.5
            else "elevated" if (top1 or 0) >= 0.35
            else "low" if top1 is not None else None),
        "pricing_power_durability": None,  # needs margin trend —
                                           # filled by caller
    }


def horizon_view(exposure: dict[str, dict],
                 ecs_out: dict) -> dict[str, Any]:
    """Near-term conversion vs long-term optionality — separate
    fields per the spec, never blended."""
    near = sum(d["weight"] for d in exposure.values()
               if d.get("horizon") == "0-18m" and d["best_e"] >= 3)
    tot = sum(d["weight"] for d in exposure.values())
    far = sum(d["weight"] for d in exposure.values()
              if d.get("horizon") in ("3-5y", "5-7y"))
    dom = max(exposure.items(), key=lambda kv: kv[1]["weight"],
              default=(None, {}))
    return {
        "dominant_domain": dom[0],
        "dominant_horizon": dom[1].get("horizon"),
        "near_term_exposure_share": round(near / tot, 3)
        if tot else None,
        "long_optionality_share": round(far / tot, 3) if tot else None}


def build(sym: str, products: list[dict], wins: list[dict],
          ctx: dict) -> dict[str, Any]:
    """Assemble the fdce block: exposure → ECS → transitions →
    disruption → horizon + the ctx fields the FDCS yaml consumes."""
    u = universe().get(sym.upper()) or {}
    wins_by_product = {str(w.get("product") or "").lower(): w
                       for w in (wins or [])}
    exp = domain_exposure(products, wins_by_product)
    ecs_out = ecs(products, wins_by_product)
    trans = transition_exposure(products)
    mechs = set()
    for p in products:
        mechs |= set(p.get("moat") or [])
        ev = p.get("evidence") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        mechs |= set(ev.get("moat") or [])
    dis = disruption(products, mechs, ctx.get("top1_pct"), trans)
    dis["pricing_power_durability"] = (
        "durable" if (ctx.get("om_now") or 0) >= 0.25
        and ctx.get("margin_trend") != "declining"
        else "eroding" if ctx.get("margin_trend") == "declining"
        else None)
    hv = horizon_view(exp, ecs_out)
    # next-gen rank fallback for fdce-only symbols (sector modules
    # without nextgen_layers): max stage among domain-layer products
    from app.research import products as _prod_mod
    domain_layers = set(layer_domain_map().keys())
    ng_rank = 0
    for p in products:
        lay = p.get("layer")
        if not lay:
            ev = p.get("evidence") or {}
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            lay = ev.get("layer")
        if lay in domain_layers:
            ng_rank = max(ng_rank,
                          _prod_mod._STAGE_RANK.get(
                              p.get("stage"), 0))
    return {
        "primary_domains": u.get("primary") or [],
        "secondary_domains": u.get("secondary") or [],
        "domain_exposure": exp,
        "ecs": ecs_out,
        "transitions": trans,
        "disruption": dis,
        "horizon": hv,
        "ctx": {
            "demand_score": demand_score(exp),
            "bottleneck_mechs": len(mechs & _BOTTLENECK_MECHS),
            "domain_count": len([d for d in exp.values()
                                 if d["weight"] > 0]),
            "ecs_score": ecs_out.get("ecs"),
            "nextgen_stage_rank_fdce": ng_rank,
            "prod_exposure": ecs_out.get(
                "production_exposure_pct"),
            "trans_net": trans["net"],
            "trans_delta": trans["adjusted_delta"],
        },
        "rules_version": registry_version()}


def adjusted_fdcs(fdcs: Optional[float],
                  trans_delta: Optional[float]) -> Optional[float]:
    """TRANSITION_ADJUSTED_FDCS — the second view: same capability,
    repriced for architecture change. Clipped, journaled."""
    if fdcs is None:
        return None
    return round(min(max(fdcs + (trans_delta or 0), 0), 100), 1)
