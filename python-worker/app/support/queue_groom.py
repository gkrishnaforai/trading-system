"""Queue groom — event-queue hygiene as first-class maintenance.

Not supervision: the system cleaning its own house. Runs as a regular
scheduled job so queue hygiene survives regardless of what any
external support agent is doing.

pending TTL   an event still 'pending' a day later is dead work — the
              consumer never reached it and its value decayed; mark
              'cancelled' (honest status — never 'completed') so the
              backlog can't grow silently.
terminal prune completed/cancelled/failed rows older than a week are
              deleted in bounded batches — the table is a queue with
              an audit tail, not an archive.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_PENDING_TTL_H = 24        # unconsumed past this → cancelled (dead work)
_TERMINAL_KEEP_D = 7       # completed/cancelled/failed kept this long
_PRUNE_BATCH = 50_000      # bounded delete per run — converges over runs


def run() -> dict[str, Any]:
    from app.database import db
    out = {"cancelled": 0, "pruned": 0}
    out["cancelled"] = db.execute_update(
        "UPDATE universal_events SET processing_status='cancelled',"
        " processed_at=now() WHERE processing_status='pending'"
        " AND detected_at < now() - (:h * interval '1 hour')",
        {"h": _PENDING_TTL_H})
    out["pruned"] = db.execute_update(
        "DELETE FROM universal_events WHERE event_id IN ("
        " SELECT event_id FROM universal_events"
        " WHERE processing_status IN ('completed','cancelled','failed')"
        "   AND detected_at < now() - (:d * interval '1 day')"
        " LIMIT :n)",
        {"d": _TERMINAL_KEEP_D, "n": _PRUNE_BATCH})
    if out["cancelled"] or out["pruned"]:
        logger.info("queue groom: %s", out)
    return out
