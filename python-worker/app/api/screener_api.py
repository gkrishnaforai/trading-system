"""Swing setup screener endpoints."""
from __future__ import annotations

import asyncio
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.alerts import scanner as alert_scanner
from app.screener import service

router = APIRouter()


class ScreenRequest(BaseModel):
    symbols: Optional[List[str]] = None  # default: portfolio ∪ watchlist


@router.post("/run")
async def run_screen(request: ScreenRequest | None = None):
    """Start a background setup screen. Poll GET /status for progress."""
    if service.screener_status()["running"]:
        return {"status": "already_running"}
    req = request or ScreenRequest()
    asyncio.create_task(service.run_screener_job(symbols=req.symbols))
    return {"status": "started"}


@router.get("/status")
async def screen_status():
    return service.screener_status()


@router.get("/universe")
async def screen_universe():
    """The symbol list scanned by screens and alert scans (portfolio ∪ watchlist)."""
    uni = alert_scanner.universe()
    items = sorted(
        ({"symbol": s,
          "in_portfolio": f.get("in_portfolio", False),
          "in_watchlist": f.get("in_watchlist", False)}
         for s, f in uni.items()),
        key=lambda x: (not x["in_portfolio"], x["symbol"]))
    return {"count": len(items), "items": items}


@router.get("/results")
async def screen_results():
    """Ranked setup candidates from the last screen."""
    return service.results()


@router.get("/history")
async def screen_history():
    """Past screen runs — id + timestamp + candidate count."""
    return {"runs": service.history()}


@router.get("/history/{run_id}")
async def screen_run(run_id: str):
    """Full results of one past screen run."""
    r = service.run_results(run_id)
    if not r:
        raise HTTPException(status_code=404, detail="run not found")
    return r


@router.get("/breadth")
async def screen_breadth():
    """Market-breadth series: % of universe in uptrend/downtrend per run,
    plus new-uptrend / thrust flags vs the prior run."""
    return service.breadth_history()


@router.get("/diff")
async def screen_diff():
    """Latest run vs previous: improving, deteriorating, regime migrations."""
    return service.run_diff()


@router.get("/breakout-watch")
async def breakout_watch():
    """Pre-breakout watchlist: candidates under their 20d-high pivot plus
    recent triggers. Maintained by each screen run; checked intraday."""
    return {"items": service.breakout_watch_rows()}


@router.post("/breakout-watch/refresh")
async def breakout_watch_refresh():
    """Pull live quotes for watch symbols now — fires trigger/approach
    alerts and returns updated distances."""
    res = await service.check_breakout_triggers()
    return {**res, "items": service.breakout_watch_rows()}


@router.post("/review/{symbol}")
async def review_symbol(symbol: str):
    """Full swing review for one symbol — returns the trade-card payload."""
    from app.alerts.service import run_swing_review
    run_id = uuid.uuid4().hex[:12]
    result = await run_swing_review(
        symbol.upper(), source="screener_review", run_id=run_id)
    return {"symbol": symbol.upper(), "swing_run_id": run_id,
            "result": result}
