"""Catalyst alert inbox + briefing endpoints."""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.alerts import models, scanner, service

router = APIRouter()


class ScanRequest(BaseModel):
    lookback_days: float = 0.5
    auto_review: bool = True
    max_reviews: int = service.MAX_AUTO_REVIEWS_PER_SCAN
    portfolio_only: bool = False


@router.get("/regime")
async def alerts_regime():
    """Latest market regime snapshot for the briefing header card."""
    card = service.regime_card()
    return {"regime": card, "available": card is not None}


@router.get("")
async def list_alerts(
    status: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    hours: int = Query(default=72, ge=1, le=24 * 30),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Ranked alert inbox — newest/highest priority first."""
    return {
        "count": 0,
        "items": service.inbox(status=status, symbol=symbol, hours=hours, limit=limit),
        "regime": service.regime_card(),
    }


@router.post("/scan")
async def run_scan(request: ScanRequest | None = None):
    """Start a background scan over the portfolio ∪ watchlist universe.

    Returns immediately — poll GET /scan/status for progress/result.
    The scan is idempotent (fingerprint dedup) so frequent scans are safe.
    """
    req = request or ScanRequest()
    if service.scan_status()["running"]:
        return {"status": "already_running", **service.scan_status()}
    asyncio.create_task(service.run_scan_job(
        lookback_days=req.lookback_days,
        auto_review_enabled=req.auto_review,
        max_reviews=req.max_reviews,
        portfolio_only=req.portfolio_only,
    ))
    return {"status": "started"}


@router.get("/scan/status")
async def scan_status():
    """Current/last scan job state: running flag + last result."""
    return service.scan_status()


@router.post("/{alert_id}/review")
async def review(alert_id: str):
    """Kick a background swing review for one alert — returns
    immediately; poll /{alert_id}/review/status (was synchronous and
    timed out at 120s on heavy symbols)."""
    try:
        return await service.review_alert(alert_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="alert not found")


@router.get("/{alert_id}/review/status")
async def review_status(alert_id: str):
    return service.review_status(alert_id)


@router.post("/{alert_id}/dismiss")
async def dismiss(alert_id: str):
    if not service.dismiss_alert(alert_id):
        raise HTTPException(status_code=404, detail="alert not found or already handled")
    return {"status": "dismissed", "alert_id": alert_id}


@router.get("/patterns/stats")
async def pattern_stats():
    """Empirical per-pattern performance from evaluated setup signals."""
    from app.pattern_learning import pattern_stats as stats
    return {"stats": stats()}


@router.post("/patterns/evaluate")
async def evaluate_patterns():
    """Evaluate forward outcomes for pending setup signals (cron-able daily)."""
    from app.pattern_learning import evaluate_outcomes
    return await evaluate_outcomes()


@router.get("/stats")
async def alert_outcome_stats():
    """Empirical alert performance — which event types precede moves."""
    return {"stats": service.alert_stats()}


@router.post("/evaluate")
async def evaluate_alert_outcomes():
    """Evaluate forward outcomes for pending alerts (also runs at scan tail)."""
    return await service.evaluate_alert_outcomes()
