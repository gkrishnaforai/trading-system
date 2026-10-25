"""Learned-weight writes — one audited path for every learning engine.

engine_weights        live values the engines read each run
engine_weights_log    append-only history — what changed, when, why

Every learner (meta_learn, swing_pilot, ...) writes through put() so
the audit trail is complete and identical across engines. The log
write is non-fatal: engine_weights is the contract, the log is
history — a missing audit table must never abort a learn loop.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def put(key: str, payload: dict[str, Any], by: str) -> None:
    """Upsert a learned weight + append the audit row.

    `payload` is stored verbatim in engine_weights.value; callers
    should include evidence fields (n, med, lift, ...) — `n` and
    `win_rate` are also projected into the log's own columns.
    """
    from app.database import db
    body = {"by": by, **payload}
    blob = json.dumps(body, default=str)
    db.execute_update(
        "INSERT INTO engine_weights (key, value, n, win_rate,"
        " updated_at) VALUES (:k, CAST(:v AS jsonb), :n, :w, now())"
        " ON CONFLICT (key) DO UPDATE SET"
        " value=CAST(:v AS jsonb), n=:n, win_rate=:w,"
        " updated_at=now()",
        {"k": key, "v": blob,
         "n": body.get("n"), "w": body.get("win_rate")})
    try:
        db.execute_update(
            "INSERT INTO engine_weights_log (key, value, n, win_rate)"
            " VALUES (:k, CAST(:v AS jsonb), :n, :w)",
            {"k": key, "v": blob,
             "n": body.get("n"), "w": body.get("win_rate")})
    except Exception:
        logger.warning("engine_weights_log write failed for %s", key)
