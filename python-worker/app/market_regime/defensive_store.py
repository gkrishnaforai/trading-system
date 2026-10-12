"""Persistence for daily defensive-state snapshots — mirror of
transition_store.py, plus the streak queries hysteresis needs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from app.database import db

from .defensive import DefensiveTransitionAssessment


class DefensiveTransitionStore:
    def history_for(self, as_of: datetime, *, limit: int = 40
                    ) -> list[dict[str, Any]]:
        """Nearest-of-{1,5,20}d prior scores — the delta offsets."""
        try:
            rows = db.execute_query(
                """
                SELECT as_of, score
                FROM market_defensive_snapshots
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
                previous = datetime.fromisoformat(
                    previous.replace("Z", "+00:00"))
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=timezone.utc)
            offset_days = (as_of.date() - previous.date()).days
            nearest = min((1, 5, 20),
                          key=lambda target: abs(target - offset_days))
            if abs(nearest - offset_days) <= 2:
                history.append({"offset_days": nearest,
                                "score": float(row["score"])})
        return history

    def daily(self, as_of: datetime, *, days: int = 12
              ) -> list[dict[str, Any]]:
        """Most-recent per-date score+stage rows, newest first —
        the streak window hysteresis counts over."""
        try:
            return db.execute_query(
                """
                SELECT as_of_date, score, stage
                FROM market_defensive_snapshots
                WHERE as_of_date < :d
                ORDER BY as_of_date DESC
                LIMIT :limit
                """,
                {"d": as_of.date(), "limit": days},
            ) or []
        except Exception:
            return []

    def latest(self) -> Optional[dict[str, Any]]:
        try:
            rows = db.execute_query(
                "SELECT as_of_date, score, stage, emergency, streak, "
                "components, reasons, data_sufficient "
                "FROM market_defensive_snapshots "
                "ORDER BY as_of_date DESC LIMIT 1")
            return rows[0] if rows else None
        except Exception:
            return None

    def save(self, as_of: datetime,
             assessment: DefensiveTransitionAssessment) -> None:
        try:
            db.execute_update(
                """
                INSERT INTO market_defensive_snapshots (
                    as_of_date, as_of, score, delta_1d, delta_5d,
                    delta_20d, stage, emergency, streak, components,
                    reasons, data_sufficient, rules_version, source
                ) VALUES (
                    :as_of_date, :as_of, :score, :delta_1d, :delta_5d,
                    :delta_20d, :stage, :emergency, :streak,
                    CAST(:components AS jsonb), CAST(:reasons AS jsonb),
                    :data_sufficient, :rules_version, 'deterministic'
                )
                ON CONFLICT (as_of_date) DO UPDATE SET
                    as_of = EXCLUDED.as_of,
                    score = EXCLUDED.score,
                    delta_1d = EXCLUDED.delta_1d,
                    delta_5d = EXCLUDED.delta_5d,
                    delta_20d = EXCLUDED.delta_20d,
                    stage = EXCLUDED.stage,
                    emergency = EXCLUDED.emergency,
                    streak = EXCLUDED.streak,
                    components = EXCLUDED.components,
                    reasons = EXCLUDED.reasons,
                    data_sufficient = EXCLUDED.data_sufficient,
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
                    "emergency": assessment.emergency,
                    "streak": assessment.streak,
                    "components": json.dumps(assessment.components),
                    "reasons": json.dumps(assessment.reasons),
                    "data_sufficient": assessment.data_sufficient,
                    "rules_version": assessment.rules_version,
                },
            )
        except Exception:
            return
