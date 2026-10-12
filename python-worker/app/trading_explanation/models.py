"""Reusable structured trading explanation contract."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class TradingExplanation(BaseModel):
    agent: str
    symbol: str | None = None
    action: str = "REVIEW"
    headline: str
    action_summary: str
    why: List[str] = Field(default_factory=list)
    changes_since_previous: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    next_confirmation: List[str] = Field(default_factory=list)
    data_gaps: List[str] = Field(default_factory=list)
    catalyst_direction: str | None = None
    catalyst_summary: str | None = None
    positive_catalysts: List[str] = Field(default_factory=list)
    negative_catalysts: List[str] = Field(default_factory=list)
    source: str = "deterministic_fallback"
    model: str | None = None
    prompt_version: str = "trading-explanation-v1"
