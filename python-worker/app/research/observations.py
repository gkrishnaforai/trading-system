"""Segment-revenue observations — the evidence layer that feeds the
AI-infra architecture score's growth/mix components.

Writes land in the EXISTING company_segments table (symbol, segment,
period, revenue, growth_yoy, source, as_of) — no new schema for the
observations themselves. `source` doubles as the spec's
evidence_type: 'filing' = reported, 'guidance' = management
expectation. Deterministic math (growth, mix) happens here, never
in the LLM — the LLM only extracts the fact.

Same bounded contract as products/design_wins: strict JSON,
verbatim quotes, ungrounded numbers dropped.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _claims(sym: str, limit: int = 30) -> list[dict]:
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
                if cl.get("type") in ("fact", "driver", "channel"):
                    out.append(cl)
                if len(out) >= limit:
                    return out
    except Exception as exc:
        logger.debug("observations claims %s: %s", sym, exc)
    return out


def _extract(sym: str, label: str, evidence: str) -> list[dict]:
    """Bounded LLM: claims → segment revenue observations. Guidance
    rows carry source='guidance' and their stated period — a FY27
    expectation is NEVER journaled as a reported actual."""
    try:
        from litellm import completion
        from app.config import settings
        mdl = getattr(settings, "litellm_model", None) or "gpt-4o-mini"
        resp = completion(
            model=mdl, temperature=0.1, max_tokens=1400, timeout=60,
            messages=[
                {"role": "system", "content":
                 f"You extract product/segment revenue observations "
                 f"for an {label} company. Return STRICT JSON only: "
                 "{\"segments\": [{\"segment\": str, \"period\": str, "
                 "\"revenue\": number|null, \"growth_yoy\": "
                 "number|null (decimal, e.g. 0.6 = +60%), "
                 "\"source\": \"filing\"|\"guidance\", \"quote\": "
                 "verbatim evidence substring}]}. Rules: reported "
                 "actuals → source=filing; management expectations/"
                 "targets → source=guidance with the FORWARD period "
                 "label; revenue in dollars; drop any number you "
                 "can't ground to a quote. Max 10; empty if none."},
                {"role": "user", "content":
                 f"Symbol: {sym}\nEvidence:\n{evidence}"}])
        raw = json.loads(resp.choices[0].message.content or "{}")
        out = []
        for s in (raw.get("segments") or [])[:10]:
            seg = str(s.get("segment") or "").strip()[:80]
            period = str(s.get("period") or "").strip()[:20]
            if not seg or not period:
                continue
            try:
                rev = float(s["revenue"]) if s.get("revenue") \
                    is not None else None
                g = float(s["growth_yoy"]) if s.get("growth_yoy") \
                    is not None else None
            except (TypeError, ValueError):
                continue
            if rev is None and g is None:
                continue
            src = s.get("source")
            out.append({
                "segment": seg, "period": period,
                "revenue": rev, "growth_yoy": g,
                "source": "guidance" if src == "guidance"
                          else "filing",
                "quote": str(s.get("quote") or "")[:300] or None})
        return out
    except Exception as exc:
        logger.debug("observations extract %s: %s", sym, exc)
        return []


def review(sym: str, label: str = "AI infrastructure") -> int:
    """Claims → upsert company_segments observations. Returns rows
    written. Guidance never overwrites a reported filing row for the
    same segment+period (reported is authoritative)."""
    from app.database import db
    sym = sym.upper()
    claims = _claims(sym)
    if not claims:
        return 0
    evidence = json.dumps(
        [{"type": c.get("type"), "text": c.get("text"),
          "quote": c.get("quote")} for c in claims],
        default=str)[:12000]
    written = 0
    for s in _extract(sym, label, evidence):
        try:
            # guidance yields to filing for the same key
            db.execute_update(
                "INSERT INTO company_segments (symbol, segment,"
                " period, revenue, growth_yoy, source, as_of)"
                " VALUES (:s,:g,:p,:r,:y,:src,CURRENT_DATE)"
                " ON CONFLICT (symbol, segment, period) DO UPDATE"
                " SET revenue=COALESCE(EXCLUDED.revenue,"
                "   company_segments.revenue),"
                " growth_yoy=COALESCE(EXCLUDED.growth_yoy,"
                "   company_segments.growth_yoy),"
                " source=CASE WHEN company_segments.source='filing'"
                "  THEN 'filing' ELSE EXCLUDED.source END",
                {"s": sym, "g": s["segment"], "p": s["period"],
                 "r": s["revenue"], "y": s["growth_yoy"],
                 "src": s["source"]})
            written += 1
        except Exception as exc:
            logger.debug("observations upsert %s: %s", sym, exc)
    return written


def exposure(sym: str, terms: list[str],
             total_rev: Optional[float] = None) -> dict[str, Any]:
    """Deterministic exposure read: latest-period company_segments
    rows whose segment name matches any exposure term →
    {exposed_rev_growth (max YoY among matched), exposed_rev (sum),
    exposed_rev_mix (share of total revenue), segments used}.
    Missing rows → nulls, never zeros."""
    from app.database import db
    sym = sym.upper()
    if not terms:
        return {"exposed_rev_growth": None, "exposed_rev": None,
                "exposed_rev_mix": None, "exposed_segments": []}
    try:
        rows = db.execute_query(
            "SELECT segment, period, revenue, growth_yoy, source"
            " FROM company_segments WHERE symbol=:s"
            " ORDER BY as_of DESC, id DESC LIMIT 60",
            {"s": sym})
    except Exception as exc:
        logger.debug("exposure %s: %s", sym, exc)
        return {"exposed_rev_growth": None, "exposed_rev": None,
                "exposed_rev_mix": None, "exposed_segments": []}
    terms_l = [t.lower() for t in terms]
    matched = [r for r in rows if any(
        t in str(r.get("segment") or "").lower() for t in terms_l)]
    if not matched:
        return {"exposed_rev_growth": None, "exposed_rev": None,
                "exposed_rev_mix": None, "exposed_segments": []}
    growths = [float(r["growth_yoy"]) for r in matched
               if r.get("growth_yoy") is not None]
    revs = [float(r["revenue"]) for r in matched
            if r.get("revenue") is not None]
    exposed_rev = sum(revs) if revs else None
    return {
        "exposed_rev_growth": max(growths) if growths else None,
        "exposed_rev": exposed_rev,
        "exposed_rev_mix": round(exposed_rev / total_rev, 4)
        if exposed_rev and total_rev else None,
        "exposed_segments": sorted(
            {r["segment"] for r in matched})[:8],
    }
