"""Weekly LLM attribution pass over the deterministic tailwind screen.

The screen (tailwind_screen) is the facts: revisions, acceleration,
reprice gap, FV gap, theme membership. It cannot say *why* estimates
are rising — AI-linked or cyclical. This job asks the model exactly
that, once a week, in one bounded call, and journals the verdict to
tailwind_reviews for grading against realized revisions later.

Bounded-LLM rule: the model classifies only — it cannot change flags,
scores, or permissions. Unknown/unsourced output is dropped.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

_LINKAGES = ("ai_direct", "ai_indirect", "ai_adopter",
             "non_ai_cyclical", "idiosyncratic", "unclear")
_MAX_PICKS = 30            # token bound — one call, not per-symbol
_MIN_FLAGS_NEAR_MISS = 4   # near-misses worth attributing too

_PROMPT = """You are attributing the driver behind estimate-revision
momentum for a set of stocks. Each row is a deterministic screen hit:
analysts are raising estimates (revisions%), revenue is accelerating,
and the stock hasn't fully repriced (3m return vs revisions).

For EACH symbol classify the dominant repricing driver:
- ai_direct: sells compute/infra AI directly consumes (chips, power,
  cooling, networking, memory, equipment)
- ai_indirect: benefits through an AI-derived chain (energy demand,
  construction, industrials, suppliers-of-suppliers)
- ai_adopter: uses AI to improve its own economics (insurance
  underwriting, fraud, support automation) — AI is internal, not the
  product
- non_ai_cyclical: revisions driven by an ordinary cycle (refining,
  rates, commodities, reopening) — not AI
- idiosyncratic: company-specific story (turnaround, M&A, legal)
- unclear: genuinely can't tell

Reply ONLY with JSON:
{"reviews":[{"symbol":"...","linkage":"...","confidence":"high|medium|low",
"theme":"<short structural theme or null>","rationale":"<why, <=140 chars>"}]}

Classification guidance:
- Indirect supply-chain names count as ai_direct or ai_indirect, NOT
  cyclical: memory/storage for datacenters (HDD, NAND, controllers),
  semi equipment/foundries, power semis, interconnect/optics are all
  AI-linked even though the end product isn't "AI".
- "themes" in ROWS is vetted structural membership — pure/derivative
  membership in an AI theme is evidence toward AI linkage.
- gq_tailwinds > 0 means prior earnings language showed structural
  demand evidence.
- Only call non_ai_cyclical when the driver is genuinely an ordinary
  cycle (refining margins, rates, commodities, shipping).
- "unclear" is ONLY for when you cannot identify the company's
  business at all — not for "AI linkage unproven". If AI isn't the
  driver, commit to non_ai_cyclical or idiosyncratic.
- Base your call on what the company actually does — not its ticker
  narrative.

Every input symbol must appear exactly once.

ROWS: ROWS_PLACEHOLDER
"""


def _context_rows(picks: list[dict]) -> list[dict]:
    """Attach company name/industry for grounding."""
    from app.database import db
    syms = [p["symbol"] for p in picks]
    if not syms:
        return []
    rows = db.execute_query(
        "SELECT symbol, company_name, sector, industry FROM stocks "
        "WHERE symbol = ANY(:s)", {"s": syms})
    meta = {r["symbol"]: r for r in rows or []}
    out = []
    for p in picks:
        m = meta.get(p["symbol"]) or {}
        out.append({
            "symbol": p["symbol"],
            "name": m.get("company_name"),
            "sector": m.get("sector") or p.get("sector"),
            "industry": m.get("industry"),
            "revisions": f"{(p['est_revision_pct'] or 0):+.0%}",
            "price_3m": f"{(p['price_ret_63d'] or 0):+.0%}",
            "fv_gap": (f"{p['fv_gap']:+.0%}"
                       if p.get("fv_gap") is not None else "n/a"),
            "momentum": p.get("momentum_state"),
            "themes": p.get("themes") or [],
            "gq_tailwinds": (1 if p.get("tailwind_evidence") else 0),
            "known_ai_universe": p.get("known_ai", False),
        })
    return out


def _classify(rows: list[dict]) -> dict[str, dict]:
    """One bounded call → {symbol: review}; drops invalid output."""
    try:
        from litellm import completion
        from app.config import settings
        import os
        model = os.getenv("TAILWIND_MODEL") or \
            getattr(settings, "litellm_model", None) or "gpt-4o-mini"
        r = completion(
            model=model, temperature=0.1, timeout=60, max_tokens=2000,
            messages=[{"role": "user", "content": _PROMPT.replace(
                "ROWS_PLACEHOLDER", json.dumps(rows))}])
        raw = r.choices[0].message.content or ""
        js = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
        valid = {"high", "medium", "low"}
        out = {}
        for v in js.get("reviews") or []:
            sym = str(v.get("symbol") or "").upper().strip()
            link = str(v.get("linkage") or "")
            if not sym or link not in _LINKAGES:
                continue
            out[sym] = {
                "linkage": link,
                "confidence": (v.get("confidence")
                               if v.get("confidence") in valid
                               else "low"),
                "theme": (str(v["theme"])[:60]
                          if v.get("theme") else None),
                "rationale": str(v.get("rationale") or "")[:160],
            }
        return out, model
    except Exception as exc:
        logger.info("tailwind review llm unavailable (%s)", exc)
        return {}, None


def run() -> dict[str, Any]:
    """Classify this week's screen output → tailwind_reviews journal."""
    from app.database import db
    from app.signals import tailwind_screen
    scr = tailwind_screen.run()
    picks = list(scr["candidates"])
    near = [x for x in scr["rows"]
            if not x["candidate"] and x["flags_met"]
            >= _MIN_FLAGS_NEAR_MISS]
    picks += near
    picks = picks[:_MAX_PICKS]
    if not picks:
        return {"reviewed": 0, "skipped": "no picks"}
    ctx = _context_rows(picks)
    reviews, model = _classify(ctx)
    if not reviews:
        return {"reviewed": 0, "error": "llm unavailable or "
                                        "no valid output"}
    flags_by = {p["symbol"]: p for p in picks}
    today = date.today()
    n = 0
    for c in ctx:
        rev = reviews.get(c["symbol"])
        if not rev:
            continue
        row = flags_by.get(c["symbol"]) or {}
        db.execute_update(
            "INSERT INTO tailwind_reviews "
            "(as_of, symbol, linkage, confidence, theme, rationale, "
            " screen_flags, screen, model) "
            "VALUES (:d,:s,:l,:c,:t,:r,CAST(:f AS jsonb),"
            "        CAST(:sc AS jsonb),:m) "
            "ON CONFLICT (as_of, symbol) DO UPDATE SET "
            "linkage=EXCLUDED.linkage, confidence=EXCLUDED.confidence,"
            " theme=EXCLUDED.theme, rationale=EXCLUDED.rationale,"
            " screen_flags=EXCLUDED.screen_flags,"
            " screen=EXCLUDED.screen, model=EXCLUDED.model",
            {"d": today, "s": c["symbol"], "l": rev["linkage"],
             "c": rev["confidence"], "t": rev["theme"],
             "r": rev["rationale"],
             "f": json.dumps(row.get("flags") or {}, default=str),
             "sc": json.dumps(c, default=str), "m": model})
        n += 1
    counts: dict[str, int] = {}
    for v in reviews.values():
        counts[v["linkage"]] = counts.get(v["linkage"], 0) + 1
    logger.info("tailwind review: %d journaled — %s", n, counts)
    return {"reviewed": n, "picks": len(picks), "linkages": counts,
            "model": model}
