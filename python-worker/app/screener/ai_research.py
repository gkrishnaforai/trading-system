"""AI-exposure researcher — fills the two fields no API exposes:
ai_rev_pct (share of revenue from the AI engine) and ai_segments
(which reported product lines serve AI infrastructure).

Grounding: FMP has no transcripts/SEC text on this plan, so the
evidence pack is profile description + our own segment table + the
symbol's recent AI-relevant headlines + the model's company knowledge.
The output contract forces disclosure labels: a number without a
disclosed basis comes back null, never invented.

Write policy (no human task, but accountable):
- human-set values are never overwritten (checklist.ai_rev_pct_source
  == 'human' wins forever)
- agent values are re-verifiable — re-running refreshes them
- low confidence stores the research note but leaves ai_rev_pct unset
- every write carries provenance: source, confidence, evidence quotes
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

SYSTEM_ROLE = """You are a senior thematic equity-research analyst for a Rule
Breaker growth screen. You have TWO jobs:

  A) Determine the company's AI-infrastructure revenue exposure.
  B) Score the company's SECULAR growth thesis — whatever its actual
     engine is (AI infrastructure, critical-minerals reshoring,
     defense, robotics, energy transition, fintech...). A company
     does NOT need AI exposure to score well on the thesis checklist —
     MP Materials' engine is US rare-earth independence; Rivian's is
     EV platform share. Judge the real engine, not the AI angle.

DEFINITION: "AI revenue" = revenue attributable to AI infrastructure —
AI accelerators/GPUs, data-center interconnect/networking/optics, AI
server power delivery and cooling, AI memory/storage, AI cloud or
inference capacity. Automotive/industrial/consumer revenue does NOT
count unless the company explicitly attributes that revenue to AI or
data-center demand.

RULES:
1. Output STRICT JSON only — no markdown, no prose outside the schema.
2. ai_rev_pct: the % of the most recent reported revenue attributable
   to AI/data-center. Three acceptable bases, in order:
   a) explicitly disclosed (e.g. "data center $44M of $259M" → 17)
      → disclosed=true, confidence=high
   b) derivable from disclosed segment/product numbers
      → disclosed=true, confidence=medium/high
   c) NOT disclosed but the business mix makes it legible — e.g. a
      single-segment company whose products are explicitly AI/cloud
      connectivity (Astera), or a pure-play AI cloud (Nebius). Use
      your company knowledge: estimate the %, disclosed=false,
      confidence=medium, and say in basis this is model knowledge,
      not a filing.
   Return null ONLY when you genuinely cannot bound the number —
   a clean null beats a confident guess, but refusing on a company
   whose AI exposure is public knowledge wastes the research.
3. ai_segments: which of the company's OWN reported product lines serve
   AI infrastructure. Choose ONLY from the provided segment list, using
   the exact names. Empty list if none plausibly serve AI.
4. evidence: 1-3 short quotes/paraphrases with their source (e.g.
   "Q1 FY27 earnings call", "FY26 10-K", "company IR deck").
5. confidence: high = number disclosed; medium = derivable from
   disclosed figures, repeated management statements, or well-known
   business mix; low = inference only.
6. secular_engine: one line — what the AI tailwind actually is
   (e.g. "rising power density per AI rack").
7. watch_for: one line — the disclosure that would raise confidence.
8. checklist: the qualitative Rule Breaker thesis gates — each
   true/false. These are ANALYST JUDGMENTS, not disclosed numbers —
   use your general knowledge of the company freely (a well-known
   name like MP Materials or Astera should score on what you know,
   even when the evidence pack is thin):
   tam — huge expanding TAM the company can grow into
   moat — real technology differentiation / defensibility
   ai_exposure — meaningful AI revenue or committed AI roadmap exists
   vectors — multiple future growth vectors beyond the core engine
   optionality — significant 5-year optionality (new TAMs, platforms)
   proven — the secular engine is ALREADY visible in the financials —
            revenue growth is being driven by it NOW. A roadmap,
            pivot, or option is NOT proof. This gate decides
            "confirmed" status — be strict: proven=true only when the
            numbers already show it.
   Do NOT answer all-false just because the evidence pack is thin —
   score each field independently on its merits. The strict
   "disclose-or-null" rule applies to ai_rev_pct ONLY, not to
   checklist judgments. ai_exposure is the only AI-specific field;
   all other checklist fields judge the company's own secular engine.
   'traction' in the evidence pack is our computed financials — use it
   to judge proven (accelerating revenue + expanding margin = proof).

You may use your general knowledge of the company, but disclosed or
derivable evidence in the provided materials outranks memory, and every
non-null claim must name where it came from. If evidence is thin,
return nulls — a clean null is worth more than a confident guess.
"""

SCHEMA = """{
  "ai_rev_pct": <number 0-100 | null>,
  "ai_rev_pct_basis": "<how derived, e.g. 'data center $44M of $259M Q1FY27' | null>",
  "disclosed": <true|false>,
  "ai_segments": ["<exact segment names from provided list>"],
  "secular_engine": "<one line | null>",
  "evidence": ["<quote/paraphrase — source>"],
  "confidence": "high|medium|low",
  "watch_for": "<one line | null>",
  "checklist": {"tam": true|false, "moat": true|false,
                "ai_exposure": true|false, "vectors": true|false,
                "optionality": true|false, "proven": true|false}
}"""


def _evidence_pack(fmp, sym: str, segments: dict,
                   snap: Optional[dict] = None) -> dict:
    """Deterministic fetch — the text/numbers the agent reasons over."""
    pack: dict[str, Any] = {"symbol": sym}
    if snap:
        pack["traction"] = {  # our computed financials — the proof data
            "rev_growth_yoy": snap.get("rev_growth"),
            "eps_growth_yoy": snap.get("eps_growth"),
            "rev_accel_streak_quarters": snap.get("rev_streak"),
            "gross_margin": snap.get("gross_margin"),
            "gross_margin_prior_yoy": snap.get("gross_margin_prev"),
            "op_margin": snap.get("op_margin"),
            "fcf_margin": snap.get("fcf_margin"),
            "market_cap_$B": round((snap.get("market_cap") or 0) / 1e9, 1)}
    try:
        prof = fmp._make_request("/profile", {"symbol": sym}) or [{}]
        p = prof[0] if isinstance(prof, list) else prof
        pack["company"] = p.get("companyName")
        pack["description"] = (p.get("description") or "")[:1500]
        pack["sector"], pack["industry"] = p.get("sector"), p.get("industry")
    except Exception as exc:
        logger.debug("ai research %s profile failed: %s", sym, exc)
    pack["reported_segments"] = {
        n: {"revenue_$M": round(s["rev"] / 1e6, 1),
            "share": round((s.get("share") or 0), 3),
            "yoy": round(s["yoy"], 3) if s.get("yoy") is not None else None}
        for n, s in segments.items()}
    try:
        from app.database import db
        rows = db.execute_query(
            """SELECT title FROM alert_items WHERE symbol = :s
               AND created_at > now() - interval '60 days'
               AND title ~* :rx ORDER BY created_at DESC LIMIT 15""",
            {"s": sym,
             "rx": r"(^|[^a-z])ai([^a-z]|$)|artificial intelligence|"
                   r"data ?cent(er|re)|\bgpu\b|inference|agentic|"
                   r"hyperscal|\bllm\b|accelerat"})
        pack["recent_ai_headlines"] = [r["title"] for r in rows]
    except Exception:
        pack["recent_ai_headlines"] = []
    try:
        from app.database import db as _db
        rows = _db.execute_query(
            "SELECT cyclical, cyclical_rationale FROM stocks "
            "WHERE symbol=:s AND cyclical IS NOT NULL", {"s": sym})
        if rows:
            pack["business_cycle_type"] = (
                "cyclical" if rows[0]["cyclical"] else "structural")
            if rows[0].get("cyclical_rationale"):
                pack["cycle_rationale"] = rows[0]["cyclical_rationale"]
    except Exception:
        pass
    return pack


def _call_llm(pack: dict, prior: dict) -> Optional[dict]:
    from litellm import completion
    user = {
        "task": "Determine AI-infrastructure revenue exposure for this "
                "company. Return the JSON schema exactly.",
        "schema": SCHEMA,
        "evidence_pack": pack,
        "previously_recorded": {
            k: prior.get(k) for k in
            ("ai_rev_pct", "ai_segments", "ai_rev_pct_source") if prior.get(k)},
    }
    resp = completion(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYSTEM_ROLE},
                  {"role": "user", "content": json.dumps(user)}],
        temperature=0.1, max_tokens=800,
        response_format={"type": "json_object"})
    raw = resp.choices[0].message.content or ""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("ai research bad JSON: %s", raw[:200])
        return None


_ENGINE = {
    "rb": {"members": "rule_breaker_members",
           "snapshots": "rule_breaker_snapshots",
           "snap_cols": "segments, rev_growth, eps_growth, rev_streak, "
                        "gross_margin, gross_margin_prev, op_margin, "
                        "fcf_margin, market_cap"},
    "smallcap": {"members": "smallcap_members",
                 "snapshots": "smallcap_snapshots",
                 "snap_cols": "segments, rev_growth, eps_growth, "
                              "rev_streak, gross_margin, "
                              "gross_margin_prev, op_margin, "
                              "fcf_margin, market_cap"},
}


async def research_symbol(sym: str, force: bool = False,
                          engine: str = "rb") -> dict[str, Any]:
    """Research one member's AI/secular exposure and write it to the
    checklist. engine='rb' (rule breakers) or 'smallcap' (5x scout).
    Human-set values are never overwritten unless force=True."""
    from app.database import db
    from app.providers.financial_modeling_prep.client import EnhancedFMPClient
    if engine == "smallcap":
        from app.screener.smallcap import upsert_member
    else:
        from app.screener.rule_breakers import upsert_member
    tbl = _ENGINE[engine]

    rows = db.execute_query(
        f"SELECT tier, checklist FROM {tbl['members']} WHERE symbol=:s",
        {"s": sym.upper()})
    if not rows:
        return {"status": "error", "error": f"{sym} not a member"}
    mem = rows[0]
    cl = mem.get("checklist") or {}
    if (not force and cl.get("ai_rev_pct") is not None
            and cl.get("ai_rev_pct_source") != "agent"):
        # any value not explicitly agent-written is human truth —
        # the agent only refreshes its own prior estimates
        return {"status": "skipped", "reason": "human-set value"}

    fmp = EnhancedFMPClient.from_settings()
    seg_rows = db.execute_query(
        f"SELECT {tbl['snap_cols']} FROM {tbl['snapshots']} "
        "WHERE symbol=:s ORDER BY as_of DESC LIMIT 1",
        {"s": sym.upper()})
    snap = seg_rows[0] if seg_rows else {}
    segments = (snap.get("segments") or {}) or {}
    pack = _evidence_pack(fmp, sym.upper(), segments, snap)
    res = await asyncio.to_thread(_call_llm, pack, cl)
    if not res:
        return {"status": "error", "error": "no usable model output"}

    conf = res.get("confidence") or "low"
    ai_pct = res.get("ai_rev_pct")
    patch: dict[str, Any] = {
        "ai_research": {
            "basis": res.get("ai_rev_pct_basis"),
            "secular_engine": res.get("secular_engine"),
            "evidence": res.get("evidence") or [],
            "watch_for": res.get("watch_for"),
            "confidence": conf,
            "researched_at": datetime.now(timezone.utc).isoformat(),
        }}
    applied = []
    if res.get("ai_segments"):
        # only names from the company's actual reported segments count —
        # free-form model names go to the research note, not the map
        valid = {n.lower() for n in segments}
        ok = [s for s in res["ai_segments"] if s.lower() in valid]
        off = [s for s in res["ai_segments"] if s.lower() not in valid]
        if ok:
            patch["ai_segments"] = ok
            applied.append("ai_segments")
        if off:
            patch["ai_research"]["unmatched_segments"] = off
    if conf in ("high", "medium") and ai_pct is not None:
        try:
            pct = max(0.0, min(100.0, float(ai_pct)))
            patch["ai_rev_pct"] = pct
            patch["ai_rev_pct_source"] = "agent"
            applied.append("ai_rev_pct")
        except (TypeError, ValueError):
            pass
    # qualitative checklist — the agent is the analyst; per-field
    # sources mean human marks still win, and the agent can only
    # revise its own prior calls (never downgrades a human 'true').
    srcs = dict(cl.get("checklist_sources") or {})
    cl_patch = {}
    for k in ("tam", "moat", "ai_exposure", "vectors", "optionality",
              "proven"):
        if k in (res.get("checklist") or {}) and srcs.get(k) != "human":
            cl_patch[k] = bool(res["checklist"][k])
            srcs[k] = "agent"
            if conf == "low" and k == "proven":
                cl_patch[k] = False  # low-confidence proof isn't proof
    if cl_patch:
        patch.update(cl_patch)
        patch["checklist_sources"] = srcs
        applied.append("checklist")
    upsert_member(sym, mem["tier"], patch)
    return {"status": "researched", "symbol": sym.upper(),
            "applied": applied, "confidence": conf,
            "ai_rev_pct": patch.get("ai_rev_pct"),
            "ai_segments": res.get("ai_segments"),
            "research": patch["ai_research"]}


def _needs_research(cl: dict) -> bool:
    """Member needs the agent pass — no ai_rev_pct yet, or the
    checklist has never been agent-scored (no checklist_sources)."""
    if cl.get("ai_rev_pct") is None:
        return True
    return not cl.get("checklist_sources")


async def research_missing(limit: int = 2,
                           engine: str = "rb") -> dict[str, Any]:
    """Auto-fill members the agent hasn't scored — bounded per run."""
    from app.database import db
    rows = db.execute_query(
        f"SELECT symbol, checklist FROM {_ENGINE[engine]['members']} "
        "ORDER BY symbol")
    missing = [r["symbol"] for r in rows
               if _needs_research(r.get("checklist") or {})]
    done = []
    for sym in missing[:limit]:
        try:
            done.append(await asyncio.wait_for(
                research_symbol(sym, engine=engine), timeout=90))
        except Exception as exc:
            done.append({"symbol": sym, "status": "error",
                         "error": str(exc)[:100]})
    return {"status": "completed", "missing": len(missing),
            "researched": done}
