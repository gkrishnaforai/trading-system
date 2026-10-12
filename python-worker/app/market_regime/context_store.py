"""Persistence for reusable deterministic market contexts."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from app.database import db


class MarketContextStore:
    """Best-effort durable store; market calculation remains available if DB is down."""

    def latest(self, session_date: date, horizon: str = "swing") -> dict[str, Any] | None:
        try:
            rows = db.execute_query(
                """
                SELECT snapshot, facts, regime, transition,
                       strategy_environments, event_context, event_reaction,
                       as_of, session_date
                FROM market_context_snapshots
                WHERE session_date = :session_date
                  AND horizon = :horizon
                  AND rules_version = 'market-context-v1'
                ORDER BY as_of DESC
                LIMIT 1
                """,
                {"session_date": session_date, "horizon": horizon},
            )
            return rows[0] if rows else None
        except Exception:
            return None

    def save(self, *, session_date: date, as_of: datetime, horizon: str,
             snapshot: dict, facts: dict, regime: dict, transition: dict,
             strategy_environments: dict, event_context: dict | None,
             event_reaction: dict | None, provider_routes: dict) -> None:
        try:
            db.execute_update(
                """
                INSERT INTO market_context_snapshots (
                    session_date, as_of, horizon, snapshot, facts, regime,
                    transition, strategy_environments, event_context,
                    event_reaction, provider_routes, rules_version
                ) VALUES (
                    :session_date, :as_of, :horizon, CAST(:snapshot AS jsonb),
                    CAST(:facts AS jsonb), CAST(:regime AS jsonb),
                    CAST(:transition AS jsonb), CAST(:strategy_environments AS jsonb),
                    CAST(:event_context AS jsonb), CAST(:event_reaction AS jsonb),
                    CAST(:provider_routes AS jsonb), 'market-context-v1'
                )
                ON CONFLICT (session_date, horizon, rules_version) DO UPDATE SET
                    as_of = EXCLUDED.as_of,
                    snapshot = EXCLUDED.snapshot,
                    facts = EXCLUDED.facts,
                    regime = EXCLUDED.regime,
                    transition = EXCLUDED.transition,
                    strategy_environments = EXCLUDED.strategy_environments,
                    event_context = EXCLUDED.event_context,
                    event_reaction = EXCLUDED.event_reaction,
                    provider_routes = EXCLUDED.provider_routes
                """,
                {
                    "session_date": session_date,
                    "as_of": as_of,
                    "horizon": horizon,
                    "snapshot": json.dumps(snapshot),
                    "facts": json.dumps(facts),
                    "regime": json.dumps(regime),
                    "transition": json.dumps(transition),
                    "strategy_environments": json.dumps(strategy_environments),
                    "event_context": json.dumps(event_context) if event_context else None,
                    "event_reaction": json.dumps(event_reaction) if event_reaction else None,
                    "provider_routes": json.dumps(provider_routes),
                },
            )
        except Exception:
            return
