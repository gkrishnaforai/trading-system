"""Fundamentals Events API

Provides endpoints for fundamentals change events.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict, List

from app.repositories.fundamentals_change_events_repository import FundamentalsChangeEventsRepository

router = APIRouter(tags=["fundamentals-events"])


@router.get("/events/{symbol}")
async def get_symbol_fundamentals_events(symbol: str, limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    repo = FundamentalsChangeEventsRepository()
    events = repo.fetch_latest_for_symbol(symbol, limit=limit)
    return {"symbol": symbol.upper(), "events": events}
