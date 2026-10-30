"""Design-win lifecycle — the AI-infra module's core entity.

The spec's distinctions are the schema: a product announcement is
not a design win; a design win is not production revenue; production
revenue is not profitable revenue. Each journaled row carries the
stage ladder + revenue_confirmed so `dw_conversion` is deterministic
and PIT-replayable.

Bounded LLM extracts candidate wins from journaled claims + product
records; strict JSON, verbatim quotes, grounded-or-dropped — the
same provenance contract as products._extract. Deterministic stats
feed the architecture score's design_wins component.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

STAGES = ("announced", "sampling", "qualification", "production",
          "scaling")
_STAGE_RANK = {s: i + 1 for i, s in enumerate(STAGES)}  # 1..5


def _claims(sym: str, limit: int = 40) -> list[dict]:
    from app.database import db
    out = []
    try:
        for r in db.execute_query(
                "SELECT claims FROM doc_analyses WHERE symbol=:s"
                " ORDER BY created_at DESC LIMIT 8",
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
        logger.debug("design_wins claims %s: %s", sym, exc)
    return out


def _existing(sym: str) -> list[dict]:
    from app.database import db
    try:
        return [dict(r) for r in db.execute_query(
            "SELECT customer, product, stage, revenue_confirmed"
            " FROM design_wins WHERE symbol=:s",
            {"s": sym.upper()})]
    except Exception as exc:
        logger.debug("design_wins existing %s: %s", sym, exc)
        return []


def _extract(sym: str, label: str, evidence: str) -> list[dict]:
    """Bounded LLM: claims → design-win records. An announcement is
    not a win; a win needs a named/identifiable customer or platform
    plus a product. Stage must be the LOWEST defensible step —
    'sampling' stays sampling until qual-complete evidence exists."""
    try:
        from litellm import completion
        from app.config import settings
        mdl = getattr(settings, "litellm_model", None) or "gpt-4o-mini"
        resp = completion(
            model=mdl, temperature=0.1, max_tokens=1400, timeout=60,
            messages=[
                {"role": "system", "content":
                 f"You extract customer design wins for an {label} "
                 "company from journaled evidence. Return STRICT "
                 "JSON only: {\"wins\": [{\"customer\": str, "
                 "\"product\": str, \"stage\": \"announced\"|"
                 "\"sampling\"|\"qualification\"|\"production\"|"
                 "\"scaling\", \"revenue_confirmed\": bool, "
                 "\"quote\": verbatim evidence substring}]}. Rules: "
                 "a product ANNOUNCEMENT alone is not a win — "
                 "customer/platform must be identifiable (named or "
                 "'unnamed hyperscaler'); stage is the LOWEST "
                 "defensible step — no production claim without "
                 "shipment/revenue evidence; revenue_confirmed only "
                 "when the win generates recognized revenue. Max 8; "
                 "empty list if none."},
                {"role": "user", "content":
                 f"Symbol: {sym}\nEvidence:\n{evidence}"}])
        raw = json.loads(resp.choices[0].message.content or "{}")
        out = []
        for w in (raw.get("wins") or [])[:8]:
            cust, prod = str(w.get("customer") or "").strip()[:80], \
                str(w.get("product") or "").strip()[:80]
            if not cust or not prod:
                continue
            st = w.get("stage")
            out.append({
                "customer": cust, "product": prod,
                "stage": st if st in STAGES else "announced",
                "revenue_confirmed": bool(w.get("revenue_confirmed")),
                "quote": str(w.get("quote") or "")[:300] or None})
        return out
    except Exception as exc:
        logger.debug("design_wins extract %s: %s", sym, exc)
        return []


def review(sym: str, label: str = "AI infrastructure",
           products: Optional[list] = None) -> list[dict]:
    """Claims + products → upsert design_wins. Existing rows win on
    stage conflict — a confirmed-production win is never downgraded
    by a weaker new extraction (monotone lifecycle)."""
    from app.database import db
    sym = sym.upper()
    claims = _claims(sym)
    if not claims:
        return _existing(sym)
    evidence = json.dumps(
        {"products": products or [],
         "claims": [{"type": c.get("type"), "text": c.get("text"),
                     "quote": c.get("quote")} for c in claims]},
        default=str)[:12000]
    existing = {(w["customer"].lower(), w["product"].lower()): w
                for w in _existing(sym)}
    for w in _extract(sym, label, evidence):
        key = (w["customer"].lower(), w["product"].lower())
        prior = existing.get(key)
        if prior:
            # monotone: never downgrade stage or un-confirm revenue
            if _STAGE_RANK.get(w["stage"], 0) <= _STAGE_RANK.get(
                    prior["stage"], 0) and not (
                    w["revenue_confirmed"]
                    and not prior["revenue_confirmed"]):
                continue
        try:
            db.execute_update(
                "INSERT INTO design_wins (symbol, customer, product,"
                " stage, revenue_confirmed, evidence) VALUES"
                " (:s,:c,:p,:st,:rc,CAST(:e AS jsonb))"
                " ON CONFLICT (symbol, customer, product) DO UPDATE"
                " SET stage=EXCLUDED.stage,"
                " revenue_confirmed=design_wins.revenue_confirmed"
                "   OR EXCLUDED.revenue_confirmed,"
                " evidence=EXCLUDED.evidence, updated_at=now()",
                {"s": sym, "c": w["customer"], "p": w["product"],
                 "st": w["stage"], "rc": w["revenue_confirmed"],
                 "e": json.dumps({"quote": w["quote"],
                                  "source": "research_extract"})})
        except Exception as exc:
            logger.debug("design_wins upsert %s: %s", sym, exc)
    return _existing(sym)


def stats(rows: list[dict]) -> dict[str, Any]:
    """Deterministic counters the architecture score consumes.
    conversion = share of journaled wins that reached production+ —
    the spec's design_win_to_revenue_conversion."""
    prod = [w for w in rows
            if _STAGE_RANK.get(w.get("stage") or "", 0)
            >= _STAGE_RANK["production"]
            or w.get("revenue_confirmed")]
    total = len(rows)
    return {
        "dw_total": total,
        "dw_production": len(prod),
        "dw_pipeline": total - len(prod),
        "dw_customers": len({w.get("customer") for w in rows}),
        "dw_conversion": round(len(prod) / total, 2) if total
                         else None,
    }
