"""News → claims — bounded ingestion inside the research run.

Fetches a symbol's recent headlines (FMP), drops ones already
journaled or pure price-action noise, and runs the survivors through
doc_extract.analyze — the same verbatim-quote-grounded extractor
pasted docs and filings use. Claims land in doc_analyses, so
products / design-wins / observations / commitments consume them
through their existing claim readers: no second evidence path.

Bounds (all from the sector yaml):
  max_articles   — LLM calls per symbol per run
  lookback_days  — only headlines newer than this are candidates
Dedupe on url/title makes repeat runs incremental — a headline is
extracted once, not once per week.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# pure tape-chatter — a headline that says the stock moved without
# naming a business event carries no extractable evidence
_NOISE = re.compile(
    r"why .* (stock|shares) (is |are )?(up|down|moving|fell|rose|"
    r"jumped|dropped|surged|plunged)|"
    r"(stock|shares) (rise|fall|gain|drop|jump|slump|climb|tumble)"
    r"(s|ing)? by |"
    r"price target (raised|cut|lowered|increased) to|"
    r"upgraded? to |downgraded? to ", re.I)


def _pub_date(item: dict) -> date | None:
    raw = str(item.get("publishedDate") or item.get("date") or ""
            ).strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(
            raw.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt).date()
        except ValueError:
            continue
    return None


def _seen_urls(sym: str) -> set[str]:
    from app.database import db
    try:
        return {str(r["url"]).strip() for r in db.execute_query(
            "SELECT DISTINCT url FROM doc_analyses"
            " WHERE symbol=:s AND url IS NOT NULL",
            {"s": sym})}
    except Exception as exc:
        logger.debug("news dedupe %s: %s", sym, exc)
        return set()


def scan(sym: str, cfg: dict | None = None) -> dict[str, Any]:
    """One symbol's news pass → {fetched, candidates, analyzed,
    claims, skipped_seen, skipped_noise, skipped_stale,
    skipped_unfetchable}. Fail-open: provider or DB trouble returns
    zeros, never raises — a missing feed must not kill a run."""
    from app.signals import doc_extract
    cfg = cfg or {}
    max_articles = int(cfg.get("max_articles") or 4)
    lookback = int(cfg.get("lookback_days") or 10)
    stats = {"fetched": 0, "candidates": 0, "analyzed": 0,
             "claims": 0, "skipped_seen": 0, "skipped_noise": 0,
             "skipped_stale": 0, "skipped_unfetchable": 0}
    try:
        from app.providers.financial_modeling_prep import \
            enhanced_fmp_client
        items = enhanced_fmp_client.search_stock_news(sym) or []
    except Exception as exc:
        logger.info("news fetch %s: %s", sym, exc)
        return stats
    stats["fetched"] = len(items)
    if not items:
        return stats

    seen = _seen_urls(sym)
    cutoff = date.today() - timedelta(days=lookback)
    cand = []
    for it in items:
        url = str(it.get("url") or "").strip()
        title = str(it.get("title") or "").strip()
        if url and url in seen:
            stats["skipped_seen"] += 1
            continue
        d = _pub_date(it)
        if d is not None and d < cutoff:
            stats["skipped_stale"] += 1
            continue
        if _NOISE.search(title):
            stats["skipped_noise"] += 1
            continue
        cand.append((url, title,
                     str(it.get("text") or it.get("description")
                         or "").strip()))
    cand = cand[:max_articles]
    stats["candidates"] = len(cand)

    for url, title, text in cand:
        try:
            # a short provider snippet (<200 chars) is worse than a
            # real fetch — empty text lets analyze() pull the URL
            r = doc_extract.analyze(
                sym, text=text if len(text) >= 200 else "",
                url=url, title=title)
        except Exception as exc:
            logger.info("news extract %s %s: %s", sym, url[:60], exc)
            r = {"error": str(exc)[:80]}
        if r.get("error"):
            stats["skipped_unfetchable"] += 1
            continue
        stats["analyzed"] += 1
        stats["claims"] += len(r.get("claims") or [])
    return stats
