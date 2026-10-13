"""LLM evidence extraction — turns filings / earnings-call text into
structured demand-evidence claims. Drafts only: every returned claim
must pass validate_claim + human approval before it can move an axis.

The LLM extracts FACTS with provenance (signal + quote); it never
scores axes, never writes to demand_evidence, never decides.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import yaml
import os

from app.observability.logging import get_logger
from app.fair_value_v2.demand_evidence import validate_claim

logger = get_logger(__name__)

_POLICY_PATH = os.path.join(os.path.dirname(__file__),
                            "demand_profile.yaml")


def _vocabulary() -> str:
    try:
        with open(_POLICY_PATH) as f:
            sm = (yaml.safe_load(f) or {}).get("signal_map") or {}
    except Exception:
        return ""
    lines = []
    for axis, spec in sm.items():
        sigs = (spec.get("positive") or []) + (spec.get("negative") or [])
        lines.append(f"{axis}: {', '.join(sigs)}")
    return "\n".join(lines)


def extract_claims(symbol: str, text: str, source: str,
                   source_date: Optional[str] = None,
                   source_ref: Optional[str] = None
                   ) -> Optional[List[Dict[str, Any]]]:
    """Extract structured claims from a text excerpt. Returns a list
    of validated draft claims, or None when the LLM tier is
    unconfigured. Caller persists via demand_evidence.record_claim —
    drafts only, nothing here is auto-applied."""
    try:
        from litellm import completion
    except ImportError:
        return None
    from app.config import settings
    if not (settings.openai_api_key or settings.anthropic_api_key
            or getattr(settings, "litellm_proxy_url", None)):
        return None
    if not (text or "").strip():
        return []

    vocab = _vocabulary()
    prompt = f"""You are extracting EVIDENCE CLAIMS about {symbol} from a
disclosure excerpt. Extract only explicit facts — numbers, dates,
named events — never your interpretation. Each claim must map to one
signal from the controlled vocabulary:

{vocab}

Return ONLY compact JSON — a list (possibly empty):
[{{"axis": "<axis from vocabulary>",
   "signal": "<signal from vocabulary>",
   "claim": "<one-sentence fact as disclosed>",
   "value": {{"<key>": <number_or_string>}} or null,
   "confidence": "high|medium|low",
   "evidence": "<short verbatim excerpt supporting the fact>"}}]

Rules: prefer fewer, well-supported claims. A vague statement like
"demand remains strong" with no number is not a claim. Dates matter —
if the excerpt states a metric period, put it in value.period.

EXCERPT:
{text[:6000]}"""
    try:
        resp = completion(
            model=getattr(settings, "llm_model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=1200)
        raw = resp.choices[0].message.content or ""
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            return []
        items = json.loads(m.group(0))
        if not isinstance(items, list):
            return []
    except Exception as exc:
        logger.warning("llm extract failed for %s: %s", symbol, exc)
        return None

    out: List[Dict[str, Any]] = []
    for it in items[:12]:  # cap draft volume per call
        if not isinstance(it, dict):
            continue
        claim = {
            "symbol": symbol.upper(),
            "axis": it.get("axis"),
            "signal": it.get("signal"),
            "claim": it.get("claim"),
            "value": it.get("value"),
            "source": "llm_extract",
            "source_ref": (source_ref or it.get("evidence") or "")[:900],
            "source_date": source_date,
            "confidence": it.get("confidence") or "medium",
            "status": "draft",
            "extractor_version": "llm_extract_v1",
        }
        errs = validate_claim(claim)
        if not errs:
            out.append(claim)
        else:
            logger.debug("dropping invalid extracted claim %s: %s",
                         it.get("signal"), errs)
    return out
