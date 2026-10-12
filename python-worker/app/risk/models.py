"""Typed risk-engine contracts."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RiskStatus(str, Enum):
    ALLOWED = "allowed"
    REDUCED = "reduced"
    BLOCKED = "blocked"
    INSUFFICIENT_DATA = "insufficient_data"


class PortfolioConstraints(BaseModel):
    account_equity: Optional[float] = None
    current_portfolio_risk: float = Field(default=0.0, ge=0.0)
    open_trades: int = Field(default=0, ge=0)
    max_risk_per_trade: float = Field(default=0.01, gt=0.0, le=0.1)
    max_portfolio_risk: float = Field(default=0.05, gt=0.0, le=1.0)
    max_position_pct: float = Field(default=0.10, gt=0.0, le=1.0)
    max_open_trades: int = Field(default=3, ge=1)


class RiskAssessment(BaseModel):
    symbol: str
    status: RiskStatus = RiskStatus.INSUFFICIENT_DATA
    allowed: bool = False
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    risk_per_share: Optional[float] = None
    reward_risk: Optional[float] = None
    risk_amount: Optional[float] = None
    position_size_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    position_value: Optional[float] = None
    shares: Optional[int] = None
    portfolio_heat_before: float = 0.0
    portfolio_heat_after: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)
