"""Market regime models — the agent layer's contract.

Two tiers:
  MarketState    — light 8-field state (quick checks, legacy path)
  MarketSnapshot — full 6-dimension state + history offsets
  DimensionFacts — deterministic per-dimension labels (facts)
  MarketRegime   — multi-label interpretation (agent output)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RegimeLabel(str, Enum):
    BULL_LOW_VOL = "bull_low_vol"
    BULL_HIGH_VOL = "bull_high_vol"
    BULLISH_CORRECTION = "bullish_correction"
    DISTRIBUTION_RISK = "distribution_risk"   # internals weakening, unconfirmed
    DISTRIBUTION = "distribution"             # confirmed: down-vol/NL/support failure
    MACRO_RISK_OFF = "macro_risk_off"
    BEAR = "bear"
    TRANSITION = "transition"


class MarketState(BaseModel):
    """Light regime state — SPY-centric quick check."""
    spy_price: float
    ema20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    rsi: Optional[float] = None
    volume_ratio: Optional[float] = None
    breadth_pct: Optional[float] = None
    vix: Optional[float] = None
    as_of: Optional[datetime] = None
    provider: Optional[str] = None


# ---------- snapshot dimensions ----------

class TrendState(BaseModel):
    spy_price: float
    ema20: Optional[float] = None
    sma20: Optional[float] = None
    sma50: Optional[float] = None
    sma200: Optional[float] = None
    sma20_slope: Optional[float] = None    # %/day over 5d
    sma50_slope: Optional[float] = None
    sma200_slope: Optional[float] = None
    dist_ema20: Optional[float] = None     # price vs MA, fraction
    dist_sma50: Optional[float] = None
    dist_sma200: Optional[float] = None
    above_sma20: Optional[bool] = None
    above_sma50: Optional[bool] = None
    above_sma200: Optional[bool] = None
    days_below_ema20: Optional[int] = None   # persistence streak
    days_below_sma50: Optional[int] = None


class MomentumState(BaseModel):
    rsi14: Optional[float] = None
    rsi_5d_ago: Optional[float] = None
    rsi_5d_change: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    roc5: Optional[float] = None
    roc20: Optional[float] = None
    ret1: Optional[float] = None
    ret5: Optional[float] = None
    ret20: Optional[float] = None
    close_location: Optional[float] = None   # (C-L)/(H-L) last bar
    close_loc_3d: Optional[float] = None     # 3d mean — absorption


class BreadthState(BaseModel):
    universe_size: int = 0
    pct_above_sma20: Optional[float] = None
    pct_above_sma50: Optional[float] = None
    pct_above_sma200: Optional[float] = None
    advances: int = 0
    declines: int = 0
    ad_ratio: Optional[float] = None
    new_highs: int = 0
    new_lows: int = 0
    up_volume_ratio: Optional[float] = None   # up vol / total vol today
    breadth_chg_1d: Optional[float] = None    # change in pct_above_sma50
    breadth_chg_5d: Optional[float] = None
    breadth_chg_20d: Optional[float] = None


class VolatilityState(BaseModel):
    vix: Optional[float] = None
    vix_chg_1d: Optional[float] = None       # fear acceleration
    vix_chg_5d: Optional[float] = None
    vix_pctile_20d: Optional[float] = None
    vix3m: Optional[float] = None
    vxn: Optional[float] = None
    vxn_chg_5d: Optional[float] = None
    vxn_pctile_20d: Optional[float] = None
    vxn_vix_ratio: Optional[float] = None
    vix_term_ratio: Optional[float] = None    # vix3m/vix; >1 = contango
    atr: Optional[float] = None
    atr_pct: Optional[float] = None
    rvol5: Optional[float] = None             # annualized realized vol
    rvol20: Optional[float] = None


class SectorMove(BaseModel):
    symbol: str
    ret5: Optional[float] = None
    ret20: Optional[float] = None
    vs_spy5: Optional[float] = None           # sector ret5 - SPY ret5
    above_sma20: Optional[bool] = None
    above_sma50: Optional[bool] = None


class ParticipationState(BaseModel):
    sectors: List[SectorMove] = Field(default_factory=list)
    pct_sectors_above_sma20: Optional[float] = None
    pct_sectors_above_sma50: Optional[float] = None
    rel_strength_5d: Dict[str, float] = Field(default_factory=dict)  # QQQ/SOXX/IGV/IWM vs SPY
    leading: List[str] = Field(default_factory=list)   # top sectors by ret5
    lagging: List[str] = Field(default_factory=list)


class MacroInstrument(BaseModel):
    name: str
    value: Optional[float] = None
    chg1d: Optional[float] = None
    chg5d: Optional[float] = None
    chg20d: Optional[float] = None
    delta5d: Optional[float] = None        # absolute change (bp for rates)


class MacroState(BaseModel):
    instruments: Dict[str, MacroInstrument] = Field(default_factory=dict)


class StructureState(BaseModel):
    spy_higher_high: Optional[bool] = None
    spy_higher_low: Optional[bool] = None
    qqq_higher_high: Optional[bool] = None
    qqq_higher_low: Optional[bool] = None
    qqq_above_sma50: Optional[bool] = None     # confirmation-signal inputs
    soxx_ret5: Optional[float] = None
    soxx_higher_low: Optional[bool] = None
    dist_from_20d_high: Optional[float] = None
    dist_from_20d_low: Optional[float] = None
    dist_from_52w_high: Optional[float] = None


class SnapshotPoint(BaseModel):
    """One column of the history table."""
    offset_days: int                        # 0 = today
    spy: Optional[float] = None
    rsi: Optional[float] = None
    breadth_pct50: Optional[float] = None
    vix: Optional[float] = None
    us10y: Optional[float] = None


class MarketSnapshot(BaseModel):
    as_of: Optional[datetime] = None
    provider: Optional[str] = None
    trend: TrendState
    momentum: MomentumState = Field(default_factory=MomentumState)
    breadth: BreadthState = Field(default_factory=BreadthState)
    volatility: VolatilityState = Field(default_factory=VolatilityState)
    participation: ParticipationState = Field(default_factory=ParticipationState)
    macro: MacroState = Field(default_factory=MacroState)
    structure: StructureState = Field(default_factory=StructureState)
    history: List[SnapshotPoint] = Field(default_factory=list)
    coverage: Dict[str, int] = Field(default_factory=dict)  # symbols fetched per group


class DimensionFacts(BaseModel):
    """Deterministic per-dimension labels + scores — facts, not interpretation."""
    trend: str = "unknown"           # bullish | bullish_weakening | bearish | mixed
    momentum: str = "unknown"        # strong | weakening | weak | recovering | neutral
    breadth: str = "unknown"         # strong | neutral | weakening | deteriorating | improving | weak
    volatility: str = "unknown"      # low|normal|elevated|high (+_rising suffix)
    participation: str = "unknown"   # broad | narrow | rotating
    macro: str = "unknown"           # risk_on | neutral | mildly_risk_off | risk_off
    structure: str = "unknown"       # bullish | bearish | under_pressure | recovering
    scores: Dict[str, float] = Field(default_factory=dict)  # per-dimension [-1, +1]
    trend_score: Optional[float] = None         # is the market still bullish?
    deterioration_score: Optional[float] = None  # is the regime weakening? <0 = yes
    drivers: List[str] = Field(default_factory=list)


class MarketPermissions(BaseModel):
    """Deterministic Layer-1 gate: how aggressive downstream agents may be.

    Policy, not interpretation — derived from (regime, facts,
    confirmations) by permissions.py; the LLM never sets it.
    """
    aggressive_long: bool = False
    normal_long: bool = False
    selective_long: bool = False
    dip_buying: bool = False
    breakout_buying: str = "avoid"      # allowed | limited | avoid
    shorts_allowed: bool = False
    leverage: bool = False
    size_multiplier: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: List[str] = Field(default_factory=list)


class MarketRegime(BaseModel):
    """Agent output — multi-label interpretation over the facts.

    Hybrid model: `rules_regime` is the deterministic composite; `regime`
    is final (LLM may override with justification — the disagreement is
    itself a signal worth logging).
    """
    regime: RegimeLabel                          # final primary composite
    secondary_regime: Optional[RegimeLabel] = None
    direction: str = "neutral"                   # bullish | bearish | neutral
    condition: str = "transition"                # trend | correction | distribution | risk_off | bear | transition
    dimensions: Dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: str = "medium"                   # low | medium | high
    trend_score: Optional[float] = None          # [-1,+1] is the market still bullish
    deterioration_score: Optional[float] = None  # [-1,+1] is the regime weakening
    bullish_transition_score: Optional[float] = None  # 0-100: is recovery evidence increasing?
    transition_stage: str = "NO_DIP_BUYING"
    dip_buying_environment: str = "DISABLED"
    transition_delta_1d: Optional[float] = None
    transition_delta_5d: Optional[float] = None
    transition_delta_20d: Optional[float] = None
    transition_components: Dict[str, float] = Field(default_factory=dict)
    change_components: Dict[str, float] = Field(default_factory=dict)
    transition_probabilities: Dict[str, float] = Field(default_factory=dict)
    confirmation_signals: Dict[str, Dict[str, bool]] = Field(default_factory=dict)
    market_permissions: Optional[MarketPermissions] = None
    rules_regime: Optional[RegimeLabel] = None   # deterministic composite
    regime_overridden: bool = False              # LLM disagreed with rules
    override_justification: Optional[str] = None
    interpretation: str = ""
    key_drivers: List[str] = Field(default_factory=list)
    strategies_preferred: List[str] = Field(default_factory=list)
    strategies_avoid: List[str] = Field(default_factory=list)
    source: str = "rules"                        # "llm" | "rules"
    state: Optional[MarketState] = None
    snapshot: Optional[MarketSnapshot] = None
