"""LLM extraction-tier health — one cheap cached probe.

Every evidence extractor (products, design_wins, doc_extract,
challenge, relationships) is fail-soft: a dead tier returns [] and
the run looks like 'thin evidence' instead of 'extraction offline'.
This module answers 'is the tier actually reachable' once per TTL
so the run can journal `llm_tier` and the board can show it.

States: 'up' | 'down' | 'unconfigured' (no provider key/proxy at
all — the llm_extract guard's own definition)."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_cache: dict = {"checked_at": 0.0, "status": None}
_TTL = 300.0        # re-probe ≤ every 5 min — a tier can recover
                    # mid-sweep; a permanently dead tier costs one
                    # ~10s probe per 5 min, not per symbol×extractor


def configured() -> bool:
    """Provider credentials exist? Same guard llm_extract uses —
    any of the key/proxy envs is enough for litellm to route."""
    from app.config import settings
    return bool(settings.openai_api_key
                or settings.anthropic_api_key
                or getattr(settings, "litellm_proxy_url", None))


def status(refresh: bool = False) -> str:
    """'up' | 'down' | 'unconfigured' — cached for _TTL."""
    if not configured():
        _cache.update(checked_at=time.time(), status="unconfigured")
        return "unconfigured"
    now = time.time()
    if (not refresh and _cache["status"]
            and now - _cache["checked_at"] < _TTL):
        return _cache["status"]
    st = "up"
    try:
        from litellm import completion
        from app.config import settings
        completion(
            model=getattr(settings, "litellm_model", None)
            or getattr(settings, "llm_model", None)
            or "gpt-4o-mini",
            temperature=0, max_tokens=1, timeout=10,
            messages=[{"role": "user", "content": "ok"}])
    except Exception as exc:
        logger.info("llm tier probe: %s", exc)
        st = "down"
    _cache.update(checked_at=now, status=st)
    return st
