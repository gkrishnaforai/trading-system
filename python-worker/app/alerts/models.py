"""Alert item models for the catalyst alert inbox."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AlertItem(BaseModel):
    id: Optional[str] = None
    symbol: str
    event_type: str            # analyst_upgrade | analyst_downgrade | eps_revision | catalyst
    direction: str             # POSITIVE | NEGATIVE | MIXED | NEUTRAL
    materiality: str           # HIGH | MODERATE | LOW
    title: str
    detail: dict[str, Any] = {}
    fingerprint: str
    source: Optional[str] = None
    source_timestamp: Optional[datetime] = None
    in_portfolio: bool = False
    in_watchlist: bool = False
    status: str = "new"        # new | reviewed | dismissed
    priority_score: Optional[float] = None
    swing_run_id: Optional[str] = None
    swing_action: Optional[str] = None
    swing_summary: Optional[str] = None
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None


class ScanResult(BaseModel):
    scanned_symbols: int = 0
    new_alerts: int = 0
    duplicates_skipped: int = 0
    reviews_triggered: int = 0
    errors: list[str] = []
