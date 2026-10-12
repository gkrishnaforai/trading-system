"""Typed final-decision contract."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class DecisionAction(str, Enum):
    BUY = "BUY"
    BUY_SMALL = "BUY_SMALL"
    WAIT = "WAIT"
    AVOID = "AVOID"
    EXIT = "EXIT"


class TradeDecision(BaseModel):
    symbol: str
    action: DecisionAction
    entry_action: DecisionAction | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)
    vetoes: List[str] = Field(default_factory=list)
    requires_approval: bool = True
    opportunity_quality: str = "unavailable"
    fundamental_quality: str = "unavailable"
    thesis_status: str = "UNKNOWN"
    setup_readiness: str = "NOT_READY"
    entry_state: str = "WAIT"
    valuation_label: str = "unavailable"
    growth_value_class: str = "UNCLASSIFIED"
    risk_status: str = "insufficient_data"
    position_size_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    provenance: Dict[str, str] = Field(default_factory=dict)
