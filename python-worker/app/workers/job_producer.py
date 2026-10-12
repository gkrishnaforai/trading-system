"""Best-effort job producer for the shared ``ts:jobs`` Redis stream.

Mirrors the Go ``RedisStreamJobQueue`` contract (same stream key, field names,
and payload shape) so either service can enqueue jobs the stream worker
consumes. Producer calls are intentionally best-effort: a Redis outage must
never fail a user-facing write path such as adding a holding.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis

from app.config import settings
from app.observability.logging import get_logger

logger = get_logger("job_producer")

_JOB_TYPE_FAIR_VALUE_WARMUP = "fair_value_warmup"

_client: Optional[redis.Redis] = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def _xadd(job_type: str, payload: dict) -> Optional[str]:
    stream_key = os.getenv("JOB_STREAM_KEY", "ts:jobs")
    maxlen = int(os.getenv("JOB_STREAM_MAXLEN", "10000"))
    entry_id = _get_client().xadd(
        stream_key,
        {
            "job_id": str(uuid.uuid4()),
            "job_type": job_type,
            "payload": json.dumps(payload),
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        },
        maxlen=maxlen,
        approximate=True,
    )
    return entry_id


def enqueue_fair_value_warmup(
    symbol: str,
    portfolio_id: Optional[str] = None,
    force: bool = False,
) -> Optional[str]:
    """Enqueue a fair_value_warmup job so the resolver computes/persists the
    symbol's fair value in the background. Best-effort — never raises."""
    try:
        return _xadd(
            _JOB_TYPE_FAIR_VALUE_WARMUP,
            {
                "run_id": str(uuid.uuid4()),
                "portfolio_id": portfolio_id,
                "symbol": symbol.upper(),
                "force": force,
                "attempt": 1,
                "max_attempts": 3,
            },
        )
    except Exception as e:
        logger.warning(f"fair-value warm-up enqueue failed for {symbol}: {e}")
        return None
