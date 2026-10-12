"""Persistence for daily deterministic bullish-transition snapshots."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.database import db

from .transition import BullishTransitionAssessment


class MarketTransitionStore:
    def history_for(self, as_of: datetime, *, limit: int = 40) -> list[dict[str, Any]]:
        try:
            rows = db.execute_query(
                """
                SELECT as_of, score
                FROM market_transition_snapshots
                WHERE as_of < :as_of
                ORDER BY as_of DESC
                LIMIT :limit
                """,
                {"as_of": as_of, "limit": limit},
            )
        except Exception:
            return []
        history = []
        for row in rows:
            previous = row.get("as_of")
            if not previous:
                continue
            if isinstance(previous, str):
                previous = datetime.fromisoformat(previous.replace("Z", "+00:00"))
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            offset_days = (as_of.date() - previous.date()).days
            nearest = min((1, 5, 20), key=lambda target: abs(target - offset_days))
            if abs(nearest - offset_days) <= 2:
                history.append({"offset_days": nearest, "score": float(row["score"])})
        return history

    def save(self, as_of: datetime, assessment: BullishTransitionAssessment) -> None:
        try:
            db.execute_update(
                """
                INSERT INTO market_transition_snapshots (
                    as_of_date, as_of, score, delta_1d, delta_5d, delta_20d,
                    stage, dip_buying_environment, size_multiplier, components,
                    reasons, rules_version, source
                ) VALUES (
                    :as_of_date, :as_of, :score, :delta_1d, :delta_5d,
                    :delta_20d, :stage, :dip_buying_environment, :size_multiplier,
                    CAST(:components AS jsonb), CAST(:reasons AS jsonb),
                    :rules_version, 'deterministic'
                )
                ON CONFLICT (as_of_date) DO UPDATE SET
                    as_of = EXCLUDED.as_of,
                    score = EXCLUDED.score,
                    delta_1d = EXCLUDED.delta_1d,
                    delta_5d = EXCLUDED.delta_5d,
                    delta_20d = EXCLUDED.delta_20d,
                    stage = EXCLUDED.stage,
                    dip_buying_environment = EXCLUDED.dip_buying_environment,
                    size_multiplier = EXCLUDED.size_multiplier,
                    components = EXCLUDED.components,
                    reasons = EXCLUDED.reasons,
                    rules_version = EXCLUDED.rules_version
                """,
                {
                    "as_of_date": as_of.date(),
                    "as_of": as_of,
                    "score": assessment.score,
                    "delta_1d": assessment.delta_1d,
                    "delta_5d": assessment.delta_5d,
                    "delta_20d": assessment.delta_20d,
                    "stage": assessment.stage,
                    "dip_buying_environment": assessment.dip_buying_environment,
                    "size_multiplier": assessment.size_multiplier,
                    "components": json.dumps(assessment.components),
                    "reasons": json.dumps(assessment.reasons),
                    "rules_version": assessment.rules_version,
                },
            )
        except Exception:
            # Market analysis must remain available if the optional history
            # migration has not been applied or the database is unavailable.
            return
