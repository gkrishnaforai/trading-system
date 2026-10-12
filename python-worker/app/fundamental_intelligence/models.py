"""Typed contracts for multi-dimensional fundamental intelligence."""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DimensionLabel(str, Enum):
    UNAVAILABLE = "unavailable"
    EXCEPTIONAL = "exceptional"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGATIVE = "negative"
    DEEP_VALUE = "deep_value"
    VALUE = "value"
    FAIR = "fair"
    PREMIUM = "premium"
    EXTREME_PREMIUM = "extreme_premium"
    UNKNOWN = "unknown"


class BusinessType(str, Enum):
    UNKNOWN = "unknown"
    SECULAR_GROWTH = "secular_growth"
    MATURE_COMPOUNDER = "mature_compounder"
    CYCLICAL = "cyclical"
    TURNAROUND = "turnaround"
    EARLY_STAGE = "early_stage"
    ASSET_HEAVY = "asset_heavy"
    FINANCIAL = "financial"
    REIT = "reit"
    COMMODITY = "commodity"


class DimensionAssessment(BaseModel):
    label: str = DimensionLabel.UNAVAILABLE.value
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    metrics: Dict[str, Optional[float]] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)


class ValuationDiagnostics(BaseModel):
    current_price: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    price_to_sales: Optional[float] = None
    price_to_book: Optional[float] = None
    fcf_yield: Optional[float] = None
    justified_forward_pe: Optional[float] = None
    dcf_available: bool = False
    fair_value_bear: Optional[float] = None
    fair_value_base: Optional[float] = None
    fair_value_bull: Optional[float] = None
    price_vs_base_fv_pct: Optional[float] = None
    fair_value_source: Optional[str] = None
    fair_value_regime: Optional[str] = None
    valuation_label: str = DimensionLabel.UNAVAILABLE.value
    reasons: List[str] = Field(default_factory=list)


class FundamentalAssessment(BaseModel):
    symbol: str
    as_of: Optional[str] = None
    provider: Optional[str] = None
    business_type: BusinessType = BusinessType.UNKNOWN
    growth: DimensionAssessment = Field(default_factory=DimensionAssessment)
    profitability: DimensionAssessment = Field(default_factory=DimensionAssessment)
    cash_flow_quality: DimensionAssessment = Field(default_factory=DimensionAssessment)
    balance_sheet: DimensionAssessment = Field(default_factory=DimensionAssessment)
    capital_efficiency: DimensionAssessment = Field(default_factory=DimensionAssessment)
    competitive_advantage: DimensionAssessment = Field(default_factory=DimensionAssessment)
    earnings_revision: DimensionAssessment = Field(default_factory=DimensionAssessment)
    momentum: Dict[str, object] = Field(default_factory=dict)
    forward_estimates: List[Dict[str, object]] = Field(default_factory=list)
    risk: DimensionAssessment = Field(default_factory=DimensionAssessment)
    quality_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    quality_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    field_coverage: Dict[str, float] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    valuation: ValuationDiagnostics = Field(default_factory=ValuationDiagnostics)
    growth_value_class: str = "UNCLASSIFIED"
    classification_reasons: List[str] = Field(default_factory=list)
    style_tags: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    thesis: List[str] = Field(default_factory=list)
    data_quality: str = "insufficient"
    provenance: Dict[str, str] = Field(default_factory=dict)
