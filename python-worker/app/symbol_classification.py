"""Symbol-level cyclicality classification — a first-class property on
the `stocks` master table, usable by any engine.

Cyclical names (memory/storage, commodities, shipping, autos) have
boom/bust industry cycles — revenue AND margins reverse when the cycle
turns. Structural growers have a secular demand curve; sell-offs are
valuation compression, not earnings reversals.

Consumers:
  - LEAPS: cyclical → full CALL→PUT→CALL rotation allowed on technical
    stall alone; structural → puts only when fundamentals deteriorate.
  - Research packs: checklist judgments are contextual (a cyclical's
    revenue streak means something different mid-cycle).
  - UI: `cyclical` shows provenance (human > agent > seed) and any
    analysis should surface the flag rather than hide it.

Resolution order in get_cyclicality():
  human override (never expires) → seed → fresh agent verdict (<180d)
  → classify-on-sight via the model → stale row → structural default.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

AGENT_STALE_DAYS = 180

_COLS = ("cyclical, cyclical_source, cyclical_confidence, "
         "cyclical_rationale, cyclical_updated_at")


def _row(sym: str) -> Optional[dict]:
    from app.database import db
    rows = db.execute_query(
        f"SELECT {_COLS} FROM stocks WHERE symbol=:s", {"s": sym})
    return rows[0] if rows else None


def _agent_verdict(fmp, sym: str) -> Optional[dict]:
    """Ask the model whether the business is commodity-cyclical —
    evidence: profile + 8 quarters of revenue/GM so it can see an
    actual boom/bust signature, not just the sector label."""
    import json
    import re
    from litellm import completion
    try:
        prof = (fmp._make_request("/profile", {"symbol": sym})
                or [{}])[0]
        inc = fmp._make_request(
            "/income-statement",
            {"symbol": sym, "period": "quarter", "limit": 8}) or []
        revs = [round(q["revenue"] / 1e6) for q in reversed(inc)
                if q.get("revenue")]
        gms = [round(q["grossProfit"] / q["revenue"], 3)
               for q in reversed(inc)
               if q.get("grossProfit") and q.get("revenue")]
        pack = {"symbol": sym, "company": prof.get("companyName"),
                "sector": prof.get("sector"),
                "industry": prof.get("industry"),
                "description": (prof.get("description") or "")[:700],
                "quarterly_revenue_$M": revs,
                "quarterly_gross_margin": gms}
        resp = completion(
            model="gpt-4o-mini",
            messages=[{
                "role": "system",
                "content": "You classify whether a company's economics "
                "are commodity-CYCLICAL (boom/bust industry pricing "
                "cycles — revenue and margins reverse hard when the "
                "cycle turns: memory, storage, commodities, shipping, "
                "autos, semicap equipment) versus STRUCTURAL growth "
                "(secular demand curve; sell-offs are valuation "
                "compression, not earnings-cycle reversals). Judge "
                "from the business and the revenue/margin pattern — "
                "violent swings in BOTH are the cyclical fingerprint. "
                "Return strict JSON only."},
                {"role": "user", "content": json.dumps({
                    "task": "Classify cyclical vs structural. Schema: "
                            "{cyclical: bool, confidence: "
                            "high|medium|low, rationale: string<=40w}",
                    "evidence": pack})}],
            temperature=0.1, max_tokens=300,
            response_format={"type": "json_object"})
        raw = re.sub(r"^```(?:json)?|```$", "",
                     (resp.choices[0].message.content or "").strip())
        out = json.loads(raw)
        if not isinstance(out.get("cyclical"), bool):
            return None
        return out
    except Exception as exc:
        logger.debug("cyclicality agent %s failed: %s", sym, exc)
        return None


def _persist_agent(sym: str, out: dict) -> None:
    """Write an agent verdict — never overwrites a human row."""
    from app.database import db
    try:
        db.execute_query(
            "INSERT INTO stocks (symbol, cyclical, cyclical_source, "
            "cyclical_confidence, cyclical_rationale, "
            "cyclical_updated_at) "
            "VALUES (:s, :c, 'agent', :cf, :r, now()) "
            "ON CONFLICT (symbol) DO UPDATE SET "
            "cyclical=EXCLUDED.cyclical, cyclical_source='agent', "
            "cyclical_confidence=EXCLUDED.cyclical_confidence, "
            "cyclical_rationale=EXCLUDED.cyclical_rationale, "
            "cyclical_updated_at=now() "
            "WHERE stocks.cyclical_source IS DISTINCT FROM 'human'",
            {"s": sym, "c": bool(out["cyclical"]),
             "cf": out.get("confidence"),
             "r": (out.get("rationale") or "")[:400]})
    except Exception as exc:
        logger.debug("cyclicality persist %s failed: %s", sym, exc)


def get_cyclicality(fmp, sym: str) -> dict:
    """Resolve cyclical vs structural — classifies via agent on first
    sight and persists. Always returns {cyclical, source, confidence,
    rationale}."""
    sym = sym.upper().strip()
    try:
        row = _row(sym)
    except Exception as exc:
        logger.debug("cyclicality lookup %s failed: %s", sym, exc)
        row = None
    if row and row["cyclical"] is not None and (
            row["cyclical_source"] in ("human", "seed")
            or (row["cyclical_source"] == "agent"
                and row["cyclical_updated_at"]
                and row["cyclical_updated_at"]
                > datetime.now(timezone.utc)
                - timedelta(days=AGENT_STALE_DAYS))):
        return {"cyclical": bool(row["cyclical"]),
                "source": row["cyclical_source"],
                "confidence": row.get("cyclical_confidence"),
                "rationale": row.get("cyclical_rationale")}
    out = _agent_verdict(fmp, sym)
    if out is not None:
        _persist_agent(sym, out)
        return {"cyclical": bool(out["cyclical"]), "source": "agent",
                "confidence": out.get("confidence"),
                "rationale": out.get("rationale")}
    # no agent verdict — prior row (even stale) or structural default
    return {"cyclical": bool(row["cyclical"]) if row else False,
            "source": (row["cyclical_source"] + ":stale")
            if row and row.get("cyclical_source") else "default",
            "confidence": row.get("cyclical_confidence") if row else None,
            "rationale": row.get("cyclical_rationale") if row else None}


def set_cyclicality(sym: str, cyclical: bool) -> dict:
    """Human override — always wins until cleared."""
    from app.database import db
    sym = sym.upper().strip()
    db.execute_query(
        "INSERT INTO stocks (symbol, cyclical, cyclical_source, "
        "cyclical_updated_at) VALUES (:s, :c, 'human', now()) "
        "ON CONFLICT (symbol) DO UPDATE SET cyclical=EXCLUDED.cyclical,"
        " cyclical_source='human', cyclical_updated_at=now()",
        {"s": sym, "c": bool(cyclical)})
    return {"symbol": sym, "cyclical": bool(cyclical),
            "source": "human"}


def clear_cyclicality(sym: str) -> dict:
    """Clear the classification — next consumer re-classifies via the
    agent."""
    from app.database import db
    db.execute_query(
        "UPDATE stocks SET cyclical=NULL, cyclical_source=NULL, "
        "cyclical_confidence=NULL, cyclical_rationale=NULL, "
        "cyclical_updated_at=now() WHERE symbol=:s",
        {"s": sym.upper().strip()})
    return {"symbol": sym.upper(), "cleared": True}
