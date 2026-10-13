"""LLM-assisted classification suggestion — proposes, never applies.

Keyword rules are the default and stay deterministic. The LLM reads
the company profile text and proposes archetype membership where
substring matching is structurally blind (NBIS files as
'Software—Infrastructure' while the business is rented AI compute).

Output is a proposal only — a human applies it through the existing
fair_value_v2_category_overrides path. The LLM never writes the
classification itself.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from app.observability.logging import get_logger

logger = get_logger(__name__)


def _valid_categories(router) -> list:
    cats = set()
    cfg = getattr(router, "_router_cfg", None) or {}
    for rule in cfg.get("rules") or []:
        if rule.get("category"):
            cats.add(str(rule["category"]))
    cats.add(str(cfg.get("default_category") or "value"))
    return sorted(cats)


def suggest(symbol: str) -> Optional[Dict[str, Any]]:
    """Return {current, proposed, rationale, confidence, evidence} or
    None when the LLM tier isn't configured. Read-only by contract."""
    try:
        from litellm import completion
    except ImportError:
        return None
    from app.config import settings
    if not (settings.openai_api_key or settings.anthropic_api_key
            or getattr(settings, "litellm_proxy_url", None)):
        return None

    from app.fair_value_v2.feature_store.postgres_point_in_time import (
        PostgresPointInTimeFeatureStore)
    from app.fair_value_v2.service import FairValueV2Service

    store = PostgresPointInTimeFeatureStore()
    sector, industry = store.get_company_classification(symbol)
    name, description = store.get_company_profile_text(symbol)
    if not (description or name):
        return None

    router = FairValueV2Service().runner.router
    current = router.categories_for(
        symbol, sector, industry,
        company_name=name, description=description)
    valid = _valid_categories(router)

    prompt = f"""You are an equity analyst classifying a company into
valuation archetypes for a deterministic fair-value engine.

Company: {name or symbol} ({symbol})
Sector: {sector or '—'} · Industry: {industry or '—'}
Rule-based classification today: {current}
Description: {(description or '')[:1800]}

Valid archetypes: {valid}

Pick the PRIMARY archetype that best matches HOW THE COMPANY EARNS
REVENUE today — its economics, not its GICS label. A bitcoin miner
pivoting to renting AI compute is ai_infra, not technology. A
broker-dealer is financials even if it brands itself fintech. List
SECONDARY archetypes only where a material business line genuinely
fits a second bucket (NVDA = ai_infra + technology).

Return ONLY compact JSON:
{{"primary": "<one valid archetype>",
  "secondary": ["<zero or more valid archetypes>"],
  "confidence": "high|medium|low",
  "rationale": "one sentence on revenue economics",
  "evidence": ["up to 3 phrases from the description supporting it"]}}"""
    try:
        resp = completion(
            model=getattr(settings, "llm_model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=300)
        text = resp.choices[0].message.content or ""
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        out = json.loads(m.group(0))
        primary = str(out.get("primary") or "")
        if primary not in valid:
            return None
        out["secondary"] = [s for s in (out.get("secondary") or [])
                            if s in valid and s != primary]
        return {
            "symbol": symbol,
            "sector": sector, "industry": industry,
            "current": current,
            "proposed": {"primary": primary,
                         "secondary": out["secondary"]},
            "confidence": out.get("confidence"),
            "rationale": out.get("rationale"),
            "evidence": out.get("evidence") or [],
            "changed": primary != current[0],
            "source": "llm",
        }
    except Exception as e:
        logger.warning("llm classify failed for %s: %s", symbol, e)
        return None
