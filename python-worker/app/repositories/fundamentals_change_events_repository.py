"""Fundamentals Change Events Repository

Stores and retrieves fundamentals change events for symbols.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import date, datetime

from app.database import db
from app.observability.logging import get_logger

logger = get_logger(__name__)


class FundamentalsChangeEventsRepository:
    table_name = "fundamentals_change_events"

    def insert_events(self, events: List[Dict[str, Any]]) -> int:
        if not events:
            return 0

        query = f"""
            INSERT INTO {self.table_name}
            (stock_symbol, as_of_date, event_type, event_key, headline, severity, direction, evidence, recommended_action, payload)
            VALUES
            (:stock_symbol, :as_of_date, :event_type, :event_key, :headline, :severity, :direction, CAST(:evidence AS JSONB), :recommended_action, CAST(:payload AS JSONB))
            ON CONFLICT (stock_symbol, as_of_date, event_type, event_key)
            DO UPDATE SET
              headline = EXCLUDED.headline,
              severity = EXCLUDED.severity,
              direction = EXCLUDED.direction,
              evidence = EXCLUDED.evidence,
              recommended_action = EXCLUDED.recommended_action,
              payload = EXCLUDED.payload
        """

        # Ensure JSONB params are passed as JSON strings for SQLAlchemy text() casting.
        normalized: List[Dict[str, Any]] = []
        for e in events:
            if not isinstance(e, dict):
                continue
            ev = dict(e)
            ev.setdefault("evidence", None)
            ev.setdefault("payload", None)
            # db layer will handle dict params, but CAST(:x AS JSONB) expects JSON string.
            import json

            if isinstance(ev.get("evidence"), (dict, list)):
                ev["evidence"] = json.dumps(ev.get("evidence"))
            elif ev.get("evidence") is None:
                ev["evidence"] = None
            else:
                ev["evidence"] = json.dumps(ev.get("evidence"))

            if isinstance(ev.get("payload"), (dict, list)):
                ev["payload"] = json.dumps(ev.get("payload"))
            elif ev.get("payload") is None:
                ev["payload"] = None
            else:
                ev["payload"] = json.dumps(ev.get("payload"))

            normalized.append(ev)

        try:
            return db.execute_many(query, normalized)
        except Exception as e:
            logger.warning(f"Failed inserting fundamentals change events: {e}")
            raise

    def fetch_latest_for_symbol(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            return []

        try:
            query = f"""
                SELECT id, stock_symbol, as_of_date, event_type, event_key, headline, severity, direction,
                       evidence, recommended_action, payload, created_at
                FROM {self.table_name}
                WHERE stock_symbol = :symbol
                ORDER BY created_at DESC
                LIMIT :limit
            """
            return db.execute_query(query, {"symbol": symbol, "limit": int(limit)})
        except Exception as e:
            logger.warning(f"Failed fetching fundamentals change events for {symbol}: {e}")
            return []

    def fetch_latest_as_of_date(self, symbol: str) -> Optional[date]:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            return None

        rows = db.execute_query(
            f"""
            SELECT as_of_date
            FROM {self.table_name}
            WHERE stock_symbol = :symbol
            ORDER BY as_of_date DESC
            LIMIT 1
            """,
            {"symbol": symbol},
        )
        if rows:
            return rows[0].get("as_of_date")
        return None
