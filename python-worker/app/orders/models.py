"""Side-effect-free order-plan contracts."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"


class OrderPlan(BaseModel):
    plan_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(gt=0)
    limit_price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)
    target_price: Optional[float] = Field(default=None, gt=0)
    time_in_force: TimeInForce = TimeInForce.DAY
    max_slippage_bps: float = Field(default=25.0, ge=0.0, le=1000.0)
    expires_at: Optional[str] = None
    approval_required: bool = True
    reasons: List[str] = Field(default_factory=list)
