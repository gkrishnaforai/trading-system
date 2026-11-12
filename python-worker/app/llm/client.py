"""The LLM door — every litellm.completion call should go through
llm_completion(). Raw SDK defaults are hostile to a worker:
~600s/attempt × silent retries ≈ a wedged provider holding a job
thread ~20min, surfacing only as 'job timed out'.

- timeout:     hard per-attempt cap — narrative legs must degrade
               to `missing`, not stall the job
- num_retries: bounded + jittered via the caller's own try path
- breaker:     an OpenAI outage trips after 3 failures and fails
               fast for 10min instead of every call eating 45s
"""
from __future__ import annotations

import logging

import litellm
from litellm import completion

from app.utils.http_resilience import breaker, ProviderDown

logger = logging.getLogger(__name__)

# backstop for any call site not yet migrated — better 60s than 600s
litellm.request_timeout = 60


def llm_completion(*, timeout: int = 45, num_retries: int = 2,
                   **kw):
    """All LLM calls go through here. Never raw litellm.completion
    in new code (see AGENTS.md)."""
    br = breaker("llm", threshold=3, cooldown=600)
    if not br.allow():
        raise ProviderDown("llm circuit open — failing fast")
    try:
        r = completion(timeout=timeout, num_retries=num_retries, **kw)
        br.success()
        return r
    except Exception:
        br.failure()
        raise
