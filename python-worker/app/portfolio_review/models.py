"""Manual portfolio-review contracts; no execution authority."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PortfolioAction(str, Enum):
    ADD = "ADD"
    TRIM = "TRIM"
    TAKE_PROFIT = "TAKE_PROFIT"
    EXIT = "EXIT"
    HOLD = "HOLD"
    REVIEW = "REVIEW"


class PositionReview(BaseModel):
    symbol: str
    quantity: float
    current_price: Optional[float] = None
    action: PortfolioAction
    confidence: float = Field(ge=0, le=1)
    setup_type: Optional[str] = None
    opportunity_quality: Optional[str] = None
    fundamental_quality: Optional[str] = None
    event_policy: Optional[str] = None
    risk_status: Optional[str] = None
    thesis_status: str = "UNKNOWN"
    business_quality: str = "UNKNOWN"
    fundamental_momentum: str = "UNKNOWN"
    valuation_state: str = "UNKNOWN"
    entry_state: str = "WAIT"
    position_state: str = "UNKNOWN"
    action_reason: Optional[str] = None
    trim_reason: Optional[str] = None
    take_profit_reason: Optional[str] = None
    exit_reason: Optional[str] = None
    current_position: Optional[float] = None
    current_weight: Optional[float] = None
    target_position: Optional[float] = None
    target_weight: Optional[float] = None
    reduce_quantity: Optional[float] = None
    risk_approval: Optional[bool] = None
    reasons: List[str] = Field(default_factory=list)
    data_quality: str = "unknown"
    source_decision_id: Optional[str] = None


class PortfolioReviewRun(BaseModel):
    run_id: str
    portfolio_id: str
    as_of: str
    position_count: int
    actions: List[PositionReview] = Field(default_factory=list)
    persisted: bool = False
    manual_only: bool = True
    no_orders_created: bool = True
    shared_market_context_reused: bool = True
    max_concurrency: int = 3
    reasons: List[str] = Field(default_factory=list)
