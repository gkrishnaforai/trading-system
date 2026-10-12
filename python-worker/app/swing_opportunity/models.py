"""Typed contracts for deterministic swing stock opportunity analysis."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SetupType(str, Enum):
    FIRST_PULLBACK = "first_pullback"
    PULLBACK = "pullback"
    BREAKOUT = "breakout"
    BREAKOUT_RETEST = "breakout_retest"
    MEAN_REVERSION = "mean_reversion"
    EPISODIC_PIVOT = "episodic_pivot"
    TREND_CONTINUATION = "trend_continuation"
    REVERSAL = "reversal"
    RANGE = "range"
    NO_SETUP = "no_setup"


class OpportunityQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class StockTechnicals(BaseModel):
    price: Optional[float] = None
    ema20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    rsi: Optional[float] = None
    rsi2: Optional[float] = None
    trend_turn_bars: Optional[int] = None
    macd_hist: Optional[float] = None
    ret1: Optional[float] = None
    ret5: Optional[float] = None
    ret20: Optional[float] = None
    atr_pct: Optional[float] = None
    volume_ratio: Optional[float] = None
    drawdown20: Optional[float] = None
    breakout_level: Optional[float] = None
    # Bollinger measurement layer — %b = where price sits in the band
    # (>1 = above upper band = extended), bandwidth squeeze = volatility
    # compression at a 6-month low (a move is coming, direction TBD).
    sma20: Optional[float] = None
    bb_pctb: Optional[float] = None
    bb_bandwidth: Optional[float] = None
    bb_squeeze: Optional[bool] = None
    higher_high: Optional[bool] = None
    higher_low: Optional[bool] = None


class RelativeStrength(BaseModel):
    vs_spy20: Optional[float] = None
    vs_spy60: Optional[float] = None
    vs_sector20: Optional[float] = None
    tier: str = "unknown"
    sector_symbol: Optional[str] = None


class StockDataQuality(BaseModel):
    bars: int = 0
    required_bars: int = 200
    sufficient: bool = False
    provider: Optional[str] = None
    reasons: List[str] = Field(default_factory=list)


class StockAnalysis(BaseModel):
    symbol: str
    sector: Optional[str] = None
    technicals: StockTechnicals = Field(default_factory=StockTechnicals)
    relative_strength: RelativeStrength = Field(default_factory=RelativeStrength)
    sector_alignment: str = "unknown"
    data_quality: StockDataQuality = Field(default_factory=StockDataQuality)
    volume_state: str = "unknown"


class SetupAssessment(BaseModel):
    type: SetupType = SetupType.NO_SETUP
    quality: OpportunityQuality = OpportunityQuality.UNAVAILABLE
    score: float = Field(default=0.0, ge=0.0, le=100.0)
    confirmation: str = "unavailable"
    falling_knife: bool = False
    stock_permission: str = "unknown"
    detected_patterns: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


class SwingOpportunity(BaseModel):
    symbol: str
    as_of: Optional[str] = None
    market_regime: str = "unknown"
    market_condition: str = "unknown"
    swing_environment: str = "unavailable"
    swing_size_multiplier: float = Field(default=0.0, ge=0.0, le=1.0)
    stock: StockAnalysis = Field(default_factory=lambda: StockAnalysis(symbol=""))
    fundamentals: Dict[str, object] = Field(default_factory=dict)
    catalyst: Dict[str, object] = Field(default_factory=dict)
    event_policy: str = "NORMAL"
    event_new_entries_allowed: bool = True
    market_entry_permission: str = "UNKNOWN"
    bullish_transition_score: Optional[float] = None
    transition_stage: str = "UNKNOWN"
    dip_buying_environment: str = "UNKNOWN"
    setup: SetupAssessment = Field(default_factory=SetupAssessment)
    opportunity_quality: OpportunityQuality = OpportunityQuality.UNAVAILABLE
    business_quality: str = "UNKNOWN"
    thesis_status: str = "UNKNOWN"
    setup_readiness: str = "NOT_READY"
    entry_state: str = "WAIT"
    accumulation_plan: dict = Field(default_factory=dict)
    opportunity_score: float = Field(default=0.0, ge=0.0, le=100.0)
    next_step: str = "UNAVAILABLE"
    reasons: List[str] = Field(default_factory=list)
    provenance: Dict[str, str] = Field(default_factory=dict)
