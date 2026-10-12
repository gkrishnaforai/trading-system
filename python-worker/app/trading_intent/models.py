"""Explicit user/system trading policy input."""
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class TradingHorizon(str, Enum):
    DAY_TRADING = "day_trading"
    SWING = "swing"
    POSITIONAL = "positional"
    INVESTING = "investing"


class TradingMode(str, Enum):
    ANALYSIS = "analysis"
    PAPER = "paper"
    LIVE = "live"


class TradingIntent(BaseModel):
    account_equity: float = Field(gt=0)
    horizon: TradingHorizon = TradingHorizon.SWING
    mode: TradingMode = TradingMode.ANALYSIS
    universe: List[str] = Field(default_factory=list)
    max_risk_per_trade: float = Field(default=0.01, gt=0, le=0.1)
    max_portfolio_heat: float = Field(default=0.05, gt=0, le=1)
    max_open_positions: int = Field(default=5, ge=1)
    max_position_pct: float = Field(default=0.10, gt=0, le=1)
    max_daily_loss: float = Field(default=0.02, gt=0, le=1)
    allow_shorting: bool = False
    allow_leverage: bool = False
    preferred_setups: List[str] = Field(default_factory=lambda: ["pullback", "breakout"])
    approval_required: bool = True

    @field_validator("universe", mode="before")
    @classmethod
    def normalize_universe(cls, value):
        return [str(symbol).strip().upper() for symbol in (value or []) if str(symbol).strip()]
