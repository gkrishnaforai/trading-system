"""Portfolio allocation contracts."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class AllocationStatus(str, Enum):
    APPROVED = "approved"
    REDUCED = "reduced"
    BLOCKED = "blocked"
    INSUFFICIENT_DATA = "insufficient_data"


class PortfolioSnapshot(BaseModel):
    cash: float = Field(ge=0)
    equity: float = Field(gt=0)
    invested_value: float = Field(ge=0)
    portfolio_heat: float = Field(default=0.0, ge=0.0)
    open_positions: int = Field(default=0, ge=0)
    sector_exposure: Dict[str, float] = Field(default_factory=dict)
    symbol_exposure: Dict[str, float] = Field(default_factory=dict)


class AllocationResult(BaseModel):
    symbol: str
    status: AllocationStatus
    allowed: bool = False
    requested_value: float = 0.0
    allocated_value: float = 0.0
    allocated_shares: int = 0
    allocation_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_budget: float = 0.0
    remaining_heat: float = 0.0
    reasons: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    provenance: Dict[str, str] = Field(default_factory=dict)
