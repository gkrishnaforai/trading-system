"""Canonical portfolio and decision-history domain contracts.

These are storage-independent contracts. Existing API/database rows are
adapted into them; no new tables are created by this module.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    PENDING_SETTLEMENT = "PENDING_SETTLEMENT"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class DecisionAction(str, Enum):
    ADD = "ADD"
    TRIM = "TRIM"
    HOLD = "HOLD"
    EXIT = "EXIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    REVIEW = "REVIEW"
    NO_ACTION = "NO_ACTION"


class DataFreshness(str, Enum):
    FRESH = "FRESH"
    ACCEPTABLE = "ACCEPTABLE"
    STALE = "STALE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class PositionState(BaseModel):
    position_id: str
    portfolio_id: str
    symbol: str
    asset_type: str = "stock"
    side: str = "LONG"
    quantity: float = Field(ge=0)
    average_entry_price: Optional[float] = Field(default=None, ge=0)
    current_price: Optional[float] = Field(default=None, ge=0)
    current_value: Optional[float] = Field(default=None, ge=0)
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    thesis_id: Optional[str] = None
    decision_id: Optional[str] = None
    opened_at: Optional[datetime] = None
    as_of: Optional[datetime] = None
    price_as_of: Optional[datetime] = None
    status: PositionStatus = PositionStatus.UNKNOWN
    source: Optional[str] = None


class PortfolioSnapshot(BaseModel):
    portfolio_id: str
    as_of: datetime
    account_equity: Optional[float] = Field(default=None, ge=0)
    settled_cash: Optional[float] = Field(default=None, ge=0)
    unsettled_cash: Optional[float] = Field(default=None, ge=0)
    buying_power: Optional[float] = Field(default=None, ge=0)
    invested_value: Optional[float] = Field(default=None, ge=0)
    portfolio_heat: Optional[float] = Field(default=None, ge=0)
    positions: List[PositionState] = Field(default_factory=list)
    symbol_exposure: Dict[str, float] = Field(default_factory=dict)
    sector_exposure: Dict[str, float] = Field(default_factory=dict)
    price_freshness: DataFreshness = DataFreshness.UNKNOWN
    reconciliation_status: str = "UNKNOWN"
    missing_fields: List[str] = Field(default_factory=list)
    source: Optional[str] = None


class InvalidationCondition(BaseModel):
    condition_id: str
    kind: str
    expression: str
    severity: str = "HIGH"
    active: bool = True


class TradeThesis(BaseModel):
    thesis_id: str
    symbol: str
    setup_type: Optional[str] = None
    status: str = "ACTIVE"
    version: int = Field(default=1, ge=1)
    technical_score: Optional[float] = Field(default=None, ge=0, le=100)
    fundamental_score: Optional[float] = Field(default=None, ge=0, le=100)
    valuation_score: Optional[float] = Field(default=None, ge=0, le=100)
    catalyst_score: Optional[float] = Field(default=None, ge=0, le=100)
    market_environment_score: Optional[float] = Field(default=None, ge=0, le=100)
    bull_case: Optional[str] = None
    base_case: Optional[str] = None
    bear_case: Optional[str] = None
    invalidation_conditions: List[InvalidationCondition] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    source: str = "deterministic"


class DecisionSnapshot(BaseModel):
    decision_id: str
    symbol: str
    portfolio_id: Optional[str] = None
    thesis_id: Optional[str] = None
    action: DecisionAction
    decision_confidence: float = Field(ge=0, le=1)
    regime_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    outcome_probability: Optional[float] = Field(default=None, ge=0, le=1)
    market_regime: Optional[str] = None
    strategy_environment: Optional[str] = None
    setup_type: Optional[str] = None
    risk_status: Optional[str] = None
    risk_allowed: Optional[bool] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    reward_risk: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    vetoes: List[str] = Field(default_factory=list)
    rules_version: str
    model_version: Optional[str] = None
    prompt_version: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None


class TimelineEvent(BaseModel):
    event_id: str
    portfolio_id: Optional[str] = None
    symbol: Optional[str] = None
    event_type: str
    occurred_at: datetime
    decision_id: Optional[str] = None
    thesis_id: Optional[str] = None
    payload: Dict[str, object] = Field(default_factory=dict)
    source: str


class RealizedOutcome(BaseModel):
    outcome_id: str
    decision_id: Optional[str] = None
    thesis_id: Optional[str] = None
    symbol: str
    horizon: str
    as_of: datetime
    return_pct: Optional[float] = None
    pnl: Optional[float] = None
    maximum_favorable_excursion: Optional[float] = None
    maximum_adverse_excursion: Optional[float] = None
    stop_hit: Optional[bool] = None
    target_hit: Optional[bool] = None
    holding_period_days: Optional[int] = None
    fees: Optional[float] = None
    slippage: Optional[float] = None
