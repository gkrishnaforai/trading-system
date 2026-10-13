"""On-demand evidence ingestion — pull capex actuals, news and
transcripts for a group, convert to demand_evidence claims.

Trust model:
  - capex actuals: deterministic computation over FMP cash-flow data
    → enters approved (source='fmp_cashflow'). It's a measured fact,
    not an interpretation.
  - news / transcript text: LLM extraction → drafts only.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import yaml

from app.observability.logging import get_logger
from app.fair_value_v2.demand_evidence import record_claim

logger = get_logger(__name__)

_POLICY_PATH = os.path.join(os.path.dirname(__file__),
                            "demand_profile.yaml")
_CAPEX_MOVE_PCT = 0.10   # |±10%| yoy/qoq required to emit a signal


def _policy() -> Dict[str, Any]:
    try:
        with open(_POLICY_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def ingest_groups() -> Dict[str, List[str]]:
    return _policy().get("ingest_groups") or {}


# ── deterministic capex trend ──────────────────────────────────────

def capex_claim(symbol: str,
                rows: Optional[List[Dict[str, Any]]] = None
                ) -> Optional[Dict[str, Any]]:
    """Compute a capex-trend claim from quarterly cash-flow rows.
    YoY vs the same quarter last year when available, else QoQ.
    Flat (|move| < 10%) emits no claim — no signal isn't negative.
    """
    if rows is None:
        from app.providers.financial_modeling_prep.client import (
            get_fmp_client)
        rows = get_fmp_client().get_cash_flow_statement(
            symbol, period="quarter")
    q = [r for r in (rows or []) if r.get("capitalExpenditure")
         is not None and r.get("date")]
    q.sort(key=lambda r: str(r.get("date")))
    if len(q) < 2:
        return None
    latest = q[-1]
    capex = abs(float(latest["capitalExpenditure"]))
    period = f"{latest.get('period') or ''} {latest.get('fiscalYear') or ''}".strip()

    ref, basis = None, None
    # YoY: same quarter label, prior fiscal year when identifiable
    for r in reversed(q[:-1]):
        if latest.get("period") and r.get("period") == latest.get(
                "period") and r.get("fiscalYear") != latest.get(
                "fiscalYear"):
            ref, basis = r, "yoy"
            break
    if ref is None and len(q) >= 5:
        ref, basis = q[-5], "yoy"
    if ref is None:
        ref, basis = q[-2], "qoq"
    prior = abs(float(ref["capitalExpenditure"]))
    if prior <= 0:
        return None
    growth = capex / prior - 1.0
    if abs(growth) < _CAPEX_MOVE_PCT:
        return None
    return {
        "symbol": symbol.upper(),
        "axis": "capex_sensitivity",
        "signal": ("capex_actuals_up" if growth > 0
                   else "capex_actuals_down"),
        "claim": (f"{symbol.upper()} capex ${capex/1e9:.1f}B "
                  f"{period or str(latest.get('date'))[:10]} "
                  f"({growth:+.0%} {basis})"),
        "value": {"capex_usd": capex, "growth_pct": round(growth, 4),
                  "basis": basis, "period": period or None},
        "source": "fmp_cashflow",
        "source_ref": f"fmp cash-flow {latest.get('date')}",
        "source_date": str(latest.get("date")),
        "confidence": "high",
        "status": "approved",
        "extractor_version": "capex_actuals_v1",
    }


# ── text extraction (drafts only) ──────────────────────────────────

def news_claims(symbol: str, max_articles: int = 5
                ) -> List[Dict[str, Any]]:
    from app.providers.financial_modeling_prep.client import (
        get_fmp_client)
    from app.fair_value_v2.llm_extract import extract_claims
    arts = get_fmp_client().search_stock_news(symbol) or []
    out: List[Dict[str, Any]] = []
    for a in arts[:max_articles]:
        text = " ".join(filter(None, [a.get("title"),
                                      a.get("text")]))[:4000]
        if not text.strip():
            continue
        drafts = extract_claims(
            symbol, text, source="news",
            source_date=str(a.get("publishedDate") or "") or None,
            source_ref=str(a.get("url") or "")[:900])
        for d in drafts or []:
            out.append(d)
    return out


def transcript_claims(symbol: str) -> List[Dict[str, Any]]:
    """Latest earnings transcript → claims. Sends prepared remarks
    head + Q&A tail — capex/demand color lives in both."""
    from app.providers.financial_modeling_prep.client import (
        get_fmp_client)
    from app.fair_value_v2.llm_extract import extract_claims
    rows = get_fmp_client().get_earning_transcript(symbol) or []
    if not rows:
        return []
    t = rows[0]
    content = str(t.get("content") or "")
    excerpt = (content[:3500] + "\n...[middle omitted]...\n"
               + content[-2500:]) if len(content) > 6000 else content
    return extract_claims(
        symbol, excerpt, source="earnings_call",
        source_date=str(t.get("date") or "") or None,
        source_ref=f"transcript {t.get('period') or ''} "
                   f"{t.get('fiscalYear') or t.get('date') or ''}"
        ) or []


# ── orchestration ──────────────────────────────────────────────────

def ingest_group(group: str, include_news: bool = True,
                 include_transcripts: bool = False
                 ) -> Dict[str, Any]:
    """Pull evidence for a group: deterministic capex claims
    auto-approved; news/transcript extractions arrive as drafts."""
    symbols = ingest_groups().get(group)
    if symbols is None:
        return {"ok": False, "error": f"unknown group {group!r}",
                "groups": sorted(ingest_groups())}
    approved = drafts = 0
    per_symbol: Dict[str, Any] = {}
    for sym in symbols:
        got = {"capex": 0, "news_drafts": 0, "transcript_drafts": 0}
        try:
            c = capex_claim(sym)
            if c:
                res = record_claim(c)
                if res.get("ok"):
                    got["capex"] = 1
                    approved += 1
        except Exception as exc:
            logger.warning("capex ingest failed for %s: %s", sym, exc)
        if include_news:
            try:
                for d in news_claims(sym):
                    res = record_claim(d)
                    if res.get("ok"):
                        got["news_drafts"] += 1
                        drafts += 1
            except Exception as exc:
                logger.warning("news ingest failed for %s: %s",
                               sym, exc)
        if include_transcripts:
            try:
                for d in transcript_claims(sym):
                    res = record_claim(d)
                    if res.get("ok"):
                        got["transcript_drafts"] += 1
                        drafts += 1
            except Exception as exc:
                logger.warning("transcript ingest failed for %s: %s",
                               sym, exc)
        per_symbol[sym] = got
    return {"ok": True, "group": group, "symbols": symbols,
            "approved_claims": approved, "draft_claims": drafts,
            "per_symbol": per_symbol}
