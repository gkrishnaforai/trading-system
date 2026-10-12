"""Position-management decision contract; no execution authority."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class PositionAction(str, Enum):
    HOLD = "HOLD"
    TRIM = "TRIM"
    TAKE_PROFIT = "TAKE_PROFIT"
    EXIT = "EXIT"
    REVIEW = "REVIEW"


class PositionManagementAssessment(BaseModel):
    symbol: str
    position_action: PositionAction
    thesis_status: str = "UNKNOWN"
    position_state: str = "UNKNOWN"
    current_position: float = 0.0
    current_weight: Optional[float] = None
    target_position: Optional[float] = None
    target_weight: Optional[float] = None
    reduce_quantity: Optional[float] = None
    reason_code: str
    reasons: List[str] = Field(default_factory=list)
    risk_approval: Optional[bool] = None
    rules_version: str = "position-management-v1"
