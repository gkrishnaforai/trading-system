"""Deterministic staged-accumulation contract; no execution authority."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AccumulationPhase(str, Enum):
    BLOCKED = "BLOCKED"
    WATCH = "WATCH"
    STARTER = "STARTER"
    DEVELOPING = "DEVELOPING"
    CONFIRMED = "CONFIRMED"


class AccumulationPlan(BaseModel):
    symbol: str
    eligible: bool = False
    phase: AccumulationPhase = AccumulationPhase.BLOCKED
    current_position: float = 0.0
    target_position: Optional[float] = None
    remaining_position: Optional[float] = None
    current_weight: Optional[float] = None
    target_weight: Optional[float] = None
    market_size_multiplier: float = Field(default=0.0, ge=0, le=1)
    thesis_status: str = "UNKNOWN"
    fundamental_momentum: str = "UNKNOWN"
    entry_state: str = "WAIT"
    next_confirmation: List[str] = Field(default_factory=list)
    invalidation_conditions: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    rules_version: str = "accumulation-plan-v1"
