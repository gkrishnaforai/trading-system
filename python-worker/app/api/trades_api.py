"""Trade ledger endpoints — manual journal + open-position monitor."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.trades import service

router = APIRouter()


class TradeIn(BaseModel):
    symbol: str
    trade_type: str = "swing"          # investment | swing | day
    entry_price: float
    shares: float
    entry_date: Optional[str] = None
    initial_stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    setup_type: Optional[str] = None
    signal_id: Optional[str] = None
    regime_snapshot: Optional[dict] = None
    thesis: Optional[str] = None
    user_id: str = "manual"


class ExitIn(BaseModel):
    price: float
    qty: float
    reason: str = "manual"             # stop | t1 | t2 | time | regime | manual
    exit_date: Optional[str] = None


@router.post("")
async def create_trade(t: TradeIn):
    """Log a manually-placed trade."""
    return service.log_trade(t.model_dump())


@router.get("/open")
async def get_open_trades():
    """Open trades evaluated against their plan — the exit monitor."""
    from app.market_data import MarketDataService
    return {"items": await service.monitor_open_trades(MarketDataService())}


@router.post("/{trade_id}/exit")
async def exit_trade(trade_id: str, e: ExitIn):
    """Record a partial or full exit; computes realized P&L and status."""
    return service.record_exit(trade_id, e.price, e.qty, e.reason, e.exit_date)


@router.get("/summary")
async def trades_summary():
    """Realized P&L + win rate over closed trades."""
    return service.summary()
