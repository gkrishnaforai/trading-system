"""Reusable catalyst/news/earnings contract."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CatalystDirection(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class CatalystSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class CatalystSnapshot(BaseModel):
    symbol: str
    as_of: str
    next_earnings_date: Optional[str] = None
    days_to_earnings: Optional[int] = None
    earnings_session: str = "UNKNOWN"
    eps_surprise_pct: Optional[float] = None
    revenue_surprise_pct: Optional[float] = None
    recent_earnings_count: int = 0
    news_count: int = 0
    recent_news: List[Dict[str, Optional[str]]] = Field(default_factory=list)
    direction: CatalystDirection = CatalystDirection.UNKNOWN
    news_direction: CatalystDirection = CatalystDirection.UNKNOWN
    catalyst_direction: CatalystDirection = CatalystDirection.UNKNOWN
    severity: CatalystSeverity = CatalystSeverity.NONE
    catalyst_type: str = "NONE"
    materiality: str = "LOW"
    reaction_state: str = "UNKNOWN"
    price_change_1d: Optional[float] = None
    volume_ratio: Optional[float] = None
    new_entry_policy: str = "NORMAL"
    overnight_risk: str = "NORMAL"
    data_quality: str = "UNKNOWN"
    providers: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    rules_version: str = "catalyst-intelligence-v1"
