"""Canonical scheduled-market-event and reaction contracts."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MarketEventType(str, Enum):
    FOMC = "FOMC"
    CPI = "CPI"
    EMPLOYMENT = "EMPLOYMENT"
    EARNINGS = "EARNINGS"
    FDA = "FDA"
    REGULATORY = "REGULATORY"
    PRODUCT = "PRODUCT"
    OTHER = "OTHER"


class EventSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class EventStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    RELEASED = "RELEASED"
    CONFIRMED = "CONFIRMED"
    UNKNOWN = "UNKNOWN"


class PolicyBias(str, Enum):
    HAWKISH = "HAWKISH"
    DOVISH = "DOVISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class ReactionState(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    MIXED = "MIXED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class MarketEvent(BaseModel):
    event_id: str
    event_type: MarketEventType
    event_name: str
    severity: EventSeverity = EventSeverity.MODERATE
    status: EventStatus = EventStatus.UNKNOWN
    scheduled_at: Optional[datetime] = None
    actual_at: Optional[datetime] = None
    timezone: str = "UTC"
    expected: Dict[str, Optional[float]] = Field(default_factory=dict)
    actual: Dict[str, Optional[float]] = Field(default_factory=dict)
    surprise: Dict[str, Optional[float]] = Field(default_factory=dict)
    policy_bias: PolicyBias = PolicyBias.UNKNOWN
    future_policy: Dict[str, str] = Field(default_factory=dict)
    affected_symbols: List[str] = Field(default_factory=list)
    affected_sectors: List[str] = Field(default_factory=list)
    source: Optional[str] = None
    as_of: Optional[datetime] = None


class EventReaction(BaseModel):
    event_id: str
    state: ReactionState = ReactionState.NOT_AVAILABLE
    confirmation: bool = False
    observed_at: Optional[datetime] = None
    window_minutes: int = Field(default=0, ge=0)
    metrics: Dict[str, Optional[float]] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)
    source: Optional[str] = None


class EventAwareStrategyEnvironment(BaseModel):
    horizon: str
    base_quality: str
    quality: str
    score: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    long_permission: str
    short_permission: str
    breakout_permission: str
    pullback_permission: str
    size_multiplier: float = Field(ge=0.0, le=1.0)
    pacing: str
    event_severity: EventSeverity = EventSeverity.NONE
    event_policy: str = "NORMAL"
    reaction_state: ReactionState = ReactionState.NOT_AVAILABLE
    new_entries_allowed: bool = True
    data_sufficient: bool = True
    reasons: List[str] = Field(default_factory=list)
    provenance: Dict[str, str] = Field(default_factory=dict)
