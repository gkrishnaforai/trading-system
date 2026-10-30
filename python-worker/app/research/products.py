"""Product records — what the company actually sells that could
catch the AI tailwind.

Source order (all journaled): product_initiatives rows already on
file > doc_analyses claims (channel/driver/mechanism) > bounded LLM
extraction over the company profile + claims.

The LLM extracts a bounded product list — name, stage, AI usage,
moat mechanisms from the sector's allowed set — and every claim must
trace to the evidence pack. 'uses AI' is never a moat; moat tags
must come from the sector's moat_mechanisms vocabulary. Numeric
outputs are dropped if they can't ground (same contract as the
earnings narrative).

Stage vocabulary (deterministic, mapped to product_initiatives):
    revenue | rollout | partnership | pipeline | aspiration
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_STAGES = ("revenue", "rollout", "partnership", "pipeline",
           "aspiration")
# stage → the architecture-score ladder: announced=1, sampling=2,
# qualification=3, production=4, scaling=5
_STAGE_RANK = {"aspiration": 1, "pipeline": 2, "partnership": 3,
               "rollout": 4, "revenue": 5}


def _existing(sym: str) -> list[dict]:
    from app.database import db
    try:
        return [dict(r) for r in db.execute_query(
            "SELECT name, channel, segment, stage, scenario_buckets,"
            " evidence FROM product_initiatives WHERE symbol=:s"
            " AND status='active'", {"s": sym.upper()})]
    except Exception as exc:
        logger.debug("products existing %s: %s", sym, exc)
        return []


def _claims(sym: str, limit: int = 30) -> list[dict]:
    from app.database import db
    out = []
    try:
        for r in db.execute_query(
                "SELECT claims FROM doc_analyses WHERE symbol=:s"
                " ORDER BY created_at DESC LIMIT 6",
                {"s": sym.upper()}):
            c = r.get("claims")
            for cl in (json.loads(c) if isinstance(c, str)
                       else (c or [])):
                if cl.get("type") in ("channel", "driver",
                                      "mechanism", "fact"):
                    out.append(cl)
                if len(out) >= limit:
                    return out
    except Exception as exc:
        logger.debug("products claims %s: %s", sym, exc)
    return out


def _extract(sym: str, label: str, evidence: str,
             moat_vocab: list,
             layer_vocab: Optional[list] = None,
             with_importance: bool = False) -> list[dict]:
    """Bounded LLM product extraction. Strict JSON, verbatim-grounded
    quotes, null over invention — same provenance contract as
    ai_research and the earnings narrative. `layer_vocab` (sectors
    that define architecture layers) adds a product→layer tag.
    `with_importance` adds strategic_importance (0-100, evidence-
    grounded — a classification input, never a fabricated revenue
    share)."""
    layer_field = (f", \"layer\": one of {layer_vocab}|null"
                   if layer_vocab else "")
    imp_field = (", \"strategic_importance\": int 0-100|null, "
                 "\"revenue_share_pct\": number|null (ONLY if "
                 "evidence states it — never estimate)"
                 if with_importance else "")
    try:
        from litellm import completion
        from app.config import settings
        mdl = getattr(settings, "litellm_model", None) or "gpt-4o-mini"
        resp = completion(
            model=mdl, temperature=0.1, max_tokens=1400, timeout=60,
            messages=[
                {"role": "system", "content":
                 f"You map a {label} company's products/platforms "
                 "for an AI-tailwind research engine. Return STRICT "
                 "JSON only: {\"products\": [{\"name\": str, "
                 "\"stage\": \"revenue\"|\"rollout\"|\"partnership\"|"
                 "\"pipeline\"|\"aspiration\", \"ai_use\": str|null, "
                 "\"moat\": [mechanisms], \"why_it_matters\": str, "
                 "\"quote\": verbatim evidence substring|null"
                 f"{layer_field}{imp_field}" + "}]}. "
                 f"Allowed moat mechanisms ONLY: {moat_vocab}. "
                 "'uses AI' is NOT a moat — a mechanism means "
                 "proprietary data, workflow lock-in, regulatory "
                 "barrier, installed base, IP, switching cost, or "
                 "distribution. stage=revenue only if the product "
                 "sells today; aspiration = management ambition with "
                 "no product. Max 8 products; fewer, better. Empty "
                 "list if nothing concrete."},
                {"role": "user", "content":
                 f"Symbol: {sym}\nEvidence:\n{evidence}"}])
        raw = json.loads(resp.choices[0].message.content or "{}")
        prods = raw.get("products") or []
        out = []
        for p in prods[:8]:
            if not p.get("name"):
                continue
            st = p.get("stage")
            out.append({
                "name": str(p["name"])[:80],
                "stage": st if st in _STAGES else "pipeline",
                "ai_use": (str(p["ai_use"])[:160]
                           if p.get("ai_use") else None),
                "moat": [m for m in (p.get("moat") or [])
                         if m in moat_vocab],
                "layer": (str(p["layer"]) if layer_vocab
                          and p.get("layer") in layer_vocab
                          else None),
                "strategic_importance": (
                    max(0, min(int(p["strategic_importance"]), 100))
                    if with_importance
                    and isinstance(p.get("strategic_importance"),
                                   (int, float)) else None),
                "revenue_share_pct": (
                    float(p["revenue_share_pct"]) if with_importance
                    and isinstance(p.get("revenue_share_pct"),
                                   (int, float))
                    and p["revenue_share_pct"] is not None
                    else None),
                "why": str(p.get("why_it_matters") or "")[:200],
                "quote": str(p.get("quote") or "")[:300] or None,
                "synthetic": True})
        return out
    except Exception as exc:
        logger.debug("products extract %s: %s", sym, exc)
        return []


def map_products(sym: str, sector: str = "healthcare",
                 extra_layers: Optional[list] = None,
                 with_importance: bool = False) -> dict:
    """Existing initiatives + bounded extraction → canonical product
    set + the counts the scorer consumes. `extra_layers` merges a
    second layer vocabulary (the FDCE domain map) into the tagging
    space; `with_importance` asks the extractor for strategic
    importance + grounded revenue share."""
    from app.database import db
    from app.research import sectors
    sym = sym.upper()
    cfg = sectors.load(sector)
    moat_vocab = list((cfg.get("moat_mechanisms") or {}).keys())
    layer_vocab = sorted(set(
        list((cfg.get("layers") or {}).keys())
        + list(extra_layers or []))) or None
    existing = _existing(sym)
    claims = _claims(sym)
    profile = {}
    try:
        r = db.execute_query(
            "SELECT company_name, industry, sector FROM stocks"
            " WHERE symbol=:s", {"s": sym})
        profile = r[0] if r else {}
    except Exception:
        pass
    evidence = json.dumps(
        {"profile": profile,
         "existing_products": existing,
         "claims": [{"type": c.get("type"), "text": c.get("text"),
                     "quote": c.get("quote")} for c in claims]},
        default=str)[:12000]
    extracted = _extract(sym, cfg.get("label", sector), evidence,
                         moat_vocab, layer_vocab, with_importance)
    # merge: existing rows win on name collision (human/curated beats
    # synthetic); new synthetic rows upsert as stage='pipeline'+
    seen = {str(p["name"]).lower() for p in existing}
    prods = [dict(p, synthetic=False) for p in existing]
    for p in extracted:
        if p["name"].lower() in seen:
            continue
        seen.add(p["name"].lower())
        try:
            db.execute_update(
                "INSERT INTO product_initiatives (symbol, name,"
                " stage, confidence, evidence, status) VALUES"
                " (:s,:n,:st,:c,CAST(:e AS jsonb),'active')"
                " ON CONFLICT (symbol, name) DO UPDATE SET"
                " stage=EXCLUDED.stage, evidence=EXCLUDED.evidence,"
                " updated_at=now()",
                {"s": sym, "n": p["name"], "st": p["stage"],
                 "c": 0.5,
                 "e": json.dumps({"ai_use": p["ai_use"],
                                  "moat": p["moat"],
                                  "layer": p.get("layer"),
                                  "strategic_importance":
                                      p.get("strategic_importance"),
                                  "revenue_share_pct":
                                      p.get("revenue_share_pct"),
                                  "why": p["why"],
                                  "quote": p["quote"],
                                  "source": "research_extract"})})
        except Exception as exc:
            logger.debug("products upsert %s %s: %s", sym,
                         p["name"], exc)
        prods.append(p)
    # scorer counts — moat mechanisms distinct across products
    def _moats(p):
        ev = p.get("evidence") or {}
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except Exception:
                ev = {}
        return set(ev.get("moat") or p.get("moat") or [])
    mechs = set()
    for p in prods:
        mechs |= _moats(p)
    counts = {
        "products_mapped": len(prods),
        "rev_products": sum(1 for p in prods
                            if p.get("stage") == "revenue"),
        "rollout_products": sum(1 for p in prods
                                if p.get("stage") == "rollout"),
        "pipeline_products": sum(1 for p in prods if p.get("stage")
                                 in ("pipeline", "partnership",
                                     "aspiration")),
        "moat_mechs": len(mechs)}
    # next-gen transition exposure — max stage rank among products
    # tagged to the module's nextgen_layers (layers vocabulary is
    # sector-config; a sector without layers gets no rank field)
    model = sectors.classify_model(sym, sector)
    ng_layers = set(sectors.model_cfg(model, sector)
                    .get("nextgen_layers") or [])
    if ng_layers:
        def _lay(p):
            if p.get("layer"):
                return p["layer"]
            ev = p.get("evidence") or {}
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except Exception:
                    ev = {}
            return ev.get("layer")
        ng = [p for p in prods if _lay(p) in ng_layers]
        counts["nextgen_stage_rank"] = max(
            (_STAGE_RANK.get(p.get("stage"), 0) for p in ng),
            default=0)
    return {"products": prods, "counts": counts,
            "moat_mechanisms": sorted(mechs)}
