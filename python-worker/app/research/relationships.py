"""Supplier/customer relationship evidence ledger — FDCE power-chain.

Generalized, point-in-time, append-only: every row is an observation
of a commercial or corporate edge (supply, customer, ownership,
acquisition, asset transfer, industry/commodity exposure). Either
endpoint may be anonymous — confidential customers and unnamed
supplier bases are real evidence, never invented identities.

Read semantics:
  * Latest version per relationship_id wins (recorded_at order).
  * as_of replay filters recorded_at::date <= as_of — a later
    acquisition never leaks into an earlier snapshot.
  * reviewer_status separates curated truth ('approved') from
    extractor rows ('extracted' — counted, but coverage stays
    'partial' while they dominate).
  * Missing rows are descriptive 'no_data', never a negative score —
    absent evidence is not adverse evidence.

The summary block is journaled beside demand_score, NEVER into
FDCS — relationship evidence informs durability/diversification,
it does not change what the company can build or how fast the
domain grows.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_COMMERCIAL = {"commercial_supply", "commercial_customer",
               "design_win"}
_CORPORATE = {"ownership", "acquisition", "asset_transfer"}
_EXPOSURE = {"industry_exposure", "commodity_exposure"}
_VERIFIED_REVIEW = {"approved"}
_LIVE = {"announced", "active", "pending", "completed"}
_DEAD = {"terminated", "divested", "expired"}


def _latest(rows: list[dict]) -> list[dict]:
    """Newest version per relationship_id (recorded_at, id order)."""
    best: dict[str, dict] = {}
    for r in rows:
        rid = r.get("relationship_id") or str(r.get("id"))
        cur = best.get(rid)
        if cur is None or (str(r.get("recorded_at")), r.get("id")) > \
                (str(cur.get("recorded_at")), cur.get("id")):
            best[rid] = r
    return list(best.values())


def _resolve(rows: list[dict],
             include_dead: bool = False) -> list[dict]:
    """Pure resolution — latest version per edge, then drop
    terminated/expired lifecycles (divested stays visible: the
    transfer is a fact to surface, not a current relationship)."""
    out = _latest(rows)
    if not include_dead:
        out = [r for r in out
               if (r.get("lifecycle_status") or "") not in
               ("terminated", "expired")]
    return out


def edges_for(sym: str, as_of: Optional[str] = None,
              include_dead: bool = False) -> list[dict]:
    """Resolve sym's current relationship edges — rows where it is
    either endpoint, latest version each, rejected rows dropped.
    as_of limits to evidence recorded by that date (PIT replay)."""
    from app.database import db
    sym = sym.upper()
    try:
        rows = db.execute_query(
            "SELECT * FROM supplier_relationships"
            " WHERE (upper(from_symbol)=:s OR upper(to_symbol)=:s)"
            "   AND reviewer_status <> 'rejected'"
            + ("   AND recorded_at::date <= :a" if as_of else "")
            + " ORDER BY recorded_at, id",
            {"s": sym, "a": as_of} if as_of else {"s": sym})
    except Exception as exc:
        logger.debug("relationships read %s: %s", sym, exc)
        return []
    out = _resolve([dict(r) for r in rows], include_dead)
    for r in out:
        for k in ("publication_date", "source_observation_date",
                  "valid_from", "valid_to", "as_of_date",
                  "recorded_at"):
            if r.get(k) is not None:
                r[k] = str(r[k])[:19]
    return out


def _is_verified(r: dict) -> bool:
    """Approved evidence of a commercial/corporate edge —
    industry/commodity exposure rows never count as 'verified
    relationship', they're context by definition. Divested edges are
    verified facts but excluded from live relationship counts."""
    status = r.get("lifecycle_status") or ""
    return (r.get("reviewer_status") in _VERIFIED_REVIEW
            and r.get("relationship_type")
            in (_COMMERCIAL | _CORPORATE)
            and status in (_LIVE | {"divested"}))


def _edge_label(r: dict, sym: str) -> str:
    """Human-readable edge for the report — direction + counterparty
    + product. Anonymous ends show their label, never a guessed name."""
    from_side = (r.get("from_symbol") or "").upper() == sym
    other = ((r.get("to_display_label") or r.get("to_symbol") or "?")
             if from_side else
             (r.get("from_symbol") or r.get("from_display_label")
              or "anonymous counterparty"))
    direction = ("supplies" if (r.get("from_symbol") or "").upper() == sym
                 else "served by")
    prod = f" · {r['product_id']}" if r.get("product_id") else ""
    return f"{direction} {other}{prod}"


def summarize(sym: str, as_of: Optional[str] = None) -> dict[str, Any]:
    """DB read + pure summarize — the PIT replay entry point."""
    sym = sym.upper()
    try:
        edges = edges_for(sym, as_of)
    except Exception:
        edges = []
    return _summarize(sym, edges)


def _summarize(sym: str, edges: list[dict]) -> dict[str, Any]:
    """The spec §4 output block — independent fields, journaled
    beside demand_score, never into FDCS. Evidence quality is scored,
    not edge count; concentration/attribution stay 'unknown' when the
    data isn't disclosed."""
    if not edges:
        return {"relationship_status": "no_data",
                "relationship_coverage": 0.0,
                "relationship_confidence": None,
                "verified_relationship_count": 0,
                "named_customer_count": 0,
                "confidential_customer_count": 0,
                "verified_product_relationship_count": 0,
                "customer_concentration": {"top_customer_exposure": "unknown",
                                         "concentration_confidence": "low"},
                "economic_materiality": "unknown",
                "edges": []}

    verified = [r for r in edges if _is_verified(r)]
    live_verified = [r for r in verified
                     if (r.get("lifecycle_status") or "") != "divested"]
    named = [r for r in live_verified
             if r.get("relationship_type") in _COMMERCIAL
             and r.get("customer_disclosure") == "named"
             and r.get("to_symbol")]
    confidential = [r for r in live_verified
                    if r.get("customer_disclosure")
                    in ("confidential", "aggregate_only")]
    prod_keys = {(r.get("to_symbol") or r.get("to_display_label"),
                  r.get("product_id")) for r in live_verified}
    conf_vals = [int(r["evidence_confidence"]) for r in live_verified
                 if r.get("evidence_confidence") is not None]
    mats = {r.get("economic_materiality") for r in live_verified}
    mat = ("material" if "material" in mats else
           "meaningful" if "meaningful" in mats else
           "immaterial" if "immaterial" in mats else "unknown")
    n_rev = len([r for r in edges
                 if r.get("reviewer_status") in _VERIFIED_REVIEW])
    status = (
        "verified" if live_verified and n_rev == len(edges)
        else "partial" if live_verified
        else "industry_exposure_only"
        if all(r.get("relationship_type") in _EXPOSURE for r in edges)
        else "insufficient_evidence")
    n_named = len(named)
    n_conf = len(confidential)
    disc = ("high" if n_named and not n_conf else
            "medium" if n_named or n_conf else "low")
    return {
        "relationship_status": status,
        "relationship_coverage": round(n_rev / len(edges), 2),
        "relationship_confidence": max(conf_vals) if conf_vals else None,
        "verified_relationship_count": len(live_verified),
        "named_customer_count": n_named,
        "confidential_customer_count": n_conf,
        "verified_product_relationship_count": len(prod_keys),
        "customer_disclosure_confidence": disc,
        "revenue_attribution_confidence": (
            "high" if mat == "material" else
            "medium" if mat == "meaningful" else "low"),
        "customer_concentration": {
            "top_customer_exposure": "unknown",
            "concentration_confidence": "low"},
        "economic_materiality": mat,
        "edges": [{
            "relationship_id": r.get("relationship_id"),
            "type": r.get("relationship_type"),
            "subtype": r.get("relationship_subtype"),
            "lifecycle": r.get("lifecycle_status"),
            "label": _edge_label(r, sym),
            "stage": r.get("evidence_stage"),
            "confidence": r.get("evidence_confidence"),
            "disclosure": r.get("customer_disclosure"),
            "materiality": r.get("economic_materiality"),
            "verified": r.get("reviewer_status") in _VERIFIED_REVIEW,
            "as_of": r.get("as_of_date")} for r in edges],
    }


def record(edge: dict) -> Optional[int]:
    """Append one observation to the ledger — never updates history;
    a correction is a new row on the same relationship_id."""
    from app.database import db
    try:
        cols = ["relationship_id", "from_symbol", "from_entity_type",
                "from_display_label",
                "to_symbol", "to_entity_type", "to_display_label",
                "relationship_type", "relationship_subtype",
                "product_id", "product_layer",
                "evidence_stage", "evidence_confidence",
                "source_type", "source_id", "verbatim_quote",
                "publication_date", "source_observation_date",
                "customer_disclosure", "aggregate_customer_count",
                "economic_materiality", "lifecycle_status",
                "valid_from", "valid_to", "as_of_date",
                "origin", "reviewer_status", "design_win_id", "note"]
        r = db.execute_query(
            "INSERT INTO supplier_relationships ("
            + ", ".join(cols) + ") VALUES ("
            + ", ".join(f":{c}" for c in cols) + ") RETURNING id",
            {c: edge.get(c) for c in cols})
        return r[0]["id"] if r else None
    except Exception as exc:
        logger.debug("relationship record %s: %s",
                     edge.get("relationship_id"), exc)
        return None


def extract(sym: str, claims: list[dict]) -> dict[str, Any]:
    """Claims + news evidence → candidate relationship edges.

    Bounded LLM pass with the same provenance contract as
    products._extract / design_wins: verbatim quote required, drop
    ungrounded. The non-negotiable rule — a counterparty may only be
    NAMED when the quote names it; 'unnamed hyperscaler' /
    'confidential customer' phrases produce anonymous ends, never
    guessed symbols. Output lands as reviewer_status='extracted'
    (awaiting review), never auto-approved.
    """
    from litellm import completion
    from app.config import settings
    sym = sym.upper()
    if not claims:
        return {"edges": 0}
    evidence = json.dumps([
        {"type": c.get("type"), "claim": c.get("claim") or c.get("text"),
         "quote": c.get("quote"), "date": c.get("date")}
        for c in claims[:30]], default=str)[:6000]
    prompt = (
        "You extract commercial/corporate RELATIONSHIP evidence for "
        f"{sym} — supply, customer, ownership, acquisition, asset "
        "transfer edges. STRICT JSON only: {\"edges\": [{\"type\": "
        "commercial_supply|commercial_customer|ownership|acquisition|"
        "asset_transfer|industry_exposure|commodity_exposure,"
        "\"counterparty\": str|null, \"product\": str|null, "
        "\"direction\": \"from\"|\"to\", \"customer_named\": bool, "
        "\"quote\": \"verbatim\", \"date\": \"YYYY-MM-DD\"|null, "
        "\"materiality\": material|meaningful|immaterial|unknown}]}. "
        "Rules: counterparty may ONLY be a company name the quote "
        "explicitly names — 'confidential', 'unnamed', 'a hyperscaler' "
        "counterparties stay null. Quotes must appear verbatim in the "
        "evidence. No quote → drop the edge. No edges → {\"edges\":[]}.")
    try:
        r = completion(
            model=getattr(settings, "litellm_model", None)
            or "gpt-4o-mini",
            temperature=0, timeout=45, max_tokens=1200,
            messages=[{"role": "user",
                       "content": prompt + "\n\nEVIDENCE: " + evidence}])
        raw = r.choices[0].message.content or ""
        j = raw[raw.index("{"):raw.rindex("}") + 1]
        cand = json.loads(j).get("edges") or []
    except Exception as exc:
        logger.debug("relationships extract %s: %s", sym, exc)
        return {"edges": 0}

    # verbatim grounding — quotes must exist in the evidence text or
    # the edge is dropped; named counterparties must appear in their
    # own quote (a name the model invented gets dropped with it)
    ev_text = evidence.lower()
    existing = {r.get("relationship_id") for r in edges_for(
        sym, include_dead=True)}
    kept = 0
    for c in cand:
        q = str(c.get("quote") or "").strip()
        if not q or q.lower() not in ev_text:
            continue
        cp = (c.get("counterparty") or "").strip() or None
        if cp and cp.lower() not in q.lower():
            continue                    # invented name — drop
        named = bool(c.get("customer_named")) and bool(cp)
        cp_sym = cp.upper() if named else None
        supplier_out = c.get("direction") != "to"   # sym supplies cp
        rid = "rel_" + "_".join(x for x in (
            sym.lower(), (cp_sym or "anon").lower(),
            str(c.get("type") or "rel").lower()) if x)
        if rid in existing:
            continue                 # incremental: already journaled
        existing.add(rid)
        record({
            "relationship_id": rid,
            "from_symbol": sym if supplier_out else cp_sym,
            "from_entity_type": ("public_company"
                                 if supplier_out or cp_sym
                                 else "anonymous_supplier"),
            "to_symbol": cp_sym if supplier_out else sym,
            "to_entity_type": ("public_company" if named or not supplier_out
                               else "confidential_customer"),
            "to_display_label": (cp if not named and supplier_out
                                 else None),
            "relationship_type": c.get("type") or "industry_exposure",
            "relationship_subtype": (
                ("customer_named" if named else "customer_confidential")
                if supplier_out else
                ("supplier_named" if named else "supplier_confidential")),
            "product_id": c.get("product"),
            "evidence_stage": 2,
            "evidence_confidence": 60,
            "source_type": "extractor",
            "verbatim_quote": q[:600],
            "publication_date": c.get("date"),
            "customer_disclosure": ("named" if named else
                                    "confidential"),
            "economic_materiality": c.get("materiality") or "unknown",
            "lifecycle_status": "active",
            "origin": "extractor",
            "reviewer_status": "extracted"})
        kept += 1
    return {"edges": kept, "candidates": len(cand)}
