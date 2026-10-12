"""Typed contract for horizon-specific strategy environments."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class StrategyHorizon(str, Enum):
    DAY_TRADING = "day_trading"
    SWING = "swing"
    POSITIONAL = "positional"
    INVESTING = "investing"


class EnvironmentQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class StrategyEnvironment(BaseModel):
    horizon: StrategyHorizon
    quality: EnvironmentQuality
    score: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    long_permission: str = "restricted"  # allowed | limited | restricted | disabled
    short_permission: str = "restricted"
    breakout_permission: str = "restricted"
    pullback_permission: str = "restricted"
    size_multiplier: float = Field(ge=0.0, le=1.0)
    pacing: str = "staged"               # normal | staged | wait
    reasons: List[str] = Field(default_factory=list)
    required_data: List[str] = Field(default_factory=list)
    data_sufficient: bool = True
    metadata: Dict[str, str] = Field(default_factory=dict)
