"""
Event Emitter (minimal DRY)
Emits universal_events for ingestion profiles.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from app.database import db

logger = logging.getLogger(__name__)

class EventEmitter:
    """Simple emitter that writes to universal_events."""
    def emit_change_event(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        event_data: Dict[str, Any],
        previous_data: Optional[Dict[str, Any]] = None,
    ):
        """Insert a row into universal_events."""
        event_id = str(uuid4())
        payload = {
            "event_id": event_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "event_type": event_type,
            "event_timestamp": datetime.utcnow(),
            "event_data": event_data,
            "previous_data": previous_data,
        }
        # Use simple insert; ignore conflicts for now
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO universal_events (
                    event_id, entity_type, entity_id, event_type, event_timestamp,
                    event_data, previous_data
                ) VALUES (
                    CAST(%s AS uuid), %s, %s, %s, %s,
                    CAST(%s AS jsonb), CAST(%s AS jsonb)
                )
                """,
                (
                    payload["event_id"],
                    payload["entity_type"],
                    payload["entity_id"],
                    payload["event_type"],
                    payload["event_timestamp"],
                    payload["event_data"],
                    payload["previous_data"],
                ),
            )
            db.commit()
        logger.info(f"Emitted universal event {event_id} for {entity_type}:{entity_id} ({event_type})")
