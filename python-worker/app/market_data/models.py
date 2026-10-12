"""
Canonical data models — "what does the data look like", regardless of provider.

Every model carries `provider` (which source produced it) and `fetched_at`, so
provenance survives all the way up to the quant/agent layers and into Langfuse.
"""
from __future__ import annotations

from datetime import date as date_type, datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProviderPayload(BaseModel):
    """Base for anything returned by a provider. Carries provenance."""

    provider: str
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class OHLCVBar(ProviderPayload):
    symbol: str
    timestamp: datetime
    interval: str = "1d"
    open: float
    high: float
    low: float
    close: float
    adj_close: Optional[float] = None
    vwap: Optional[float] = None
    volume: Optional[float] = None


class Quote(ProviderPayload):
    symbol: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    open: Optional[float] = None
    day_low: Optional[float] = None
    day_high: Optional[float] = None
    volume: Optional[float] = None
    market_cap: Optional[float] = None
    as_of: Optional[datetime] = None


class CompanyProfile(ProviderPayload):
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    market_cap: Optional[float] = None
    beta: Optional[float] = None
    description: Optional[str] = None
    website: Optional[str] = None


class FundamentalsSnapshot(ProviderPayload):
    """Provider-agnostic fundamentals. Fields are None when the provider lacks them."""

    symbol: str
    as_of: Optional[date_type] = None

    # Valuation
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    pb_ratio: Optional[float] = None
    price_to_sales: Optional[float] = None
    peg_ratio: Optional[float] = None
    eps: Optional[float] = None

    # Profitability
    profit_margin: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None

    # Growth
    revenue_growth: Optional[float] = None
    earnings_growth: Optional[float] = None

    # Financial health
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None

    # Absolute figures
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    net_income: Optional[float] = None
    ebitda: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_debt: Optional[float] = None
    total_equity: Optional[float] = None
    total_cash: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    dividend_yield: Optional[float] = None

    # Field-level quality/provenance for derived and provider data
    coverage: Dict[str, float] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)

    # Raw provider payload for debugging / fields not yet canonicalized
    raw: Dict[str, Any] = Field(default_factory=dict, repr=False)


class FinancialStatements(ProviderPayload):
    """Statements container. Rows stay as dicts in v1 — canonicalizing the full
    statement schema is a separate piece of work; this guarantees structure."""

    symbol: str
    periodicity: str = "annual"
    income: List[Dict[str, Any]] = Field(default_factory=list)
    balance_sheet: List[Dict[str, Any]] = Field(default_factory=list)
    cash_flow: List[Dict[str, Any]] = Field(default_factory=list)
    as_of: Optional[date_type] = None


class NewsItem(ProviderPayload):
    symbol: str
    title: str
    url: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    related_symbols: List[str] = Field(default_factory=list)


class EarningsEvent(ProviderPayload):
    symbol: str
    date: Optional[date_type] = None
    eps_actual: Optional[float] = None
    eps_estimate: Optional[float] = None
    revenue_actual: Optional[float] = None
    revenue_estimate: Optional[float] = None
    fiscal_period: Optional[str] = None
    fiscal_year: Optional[int] = None


class FinancialEstimate(ProviderPayload):
    """Point-in-time forward estimate consensus from a provider."""
    symbol: str
    forecast_date: Optional[date_type] = None
    fiscal_period: str = "annual"
    fiscal_year: Optional[int] = None
    eps_avg: Optional[float] = None
    eps_low: Optional[float] = None
    eps_high: Optional[float] = None
    revenue_avg: Optional[float] = None
    revenue_low: Optional[float] = None
    revenue_high: Optional[float] = None
    analyst_count_eps: Optional[int] = None
    analyst_count_revenue: Optional[int] = None


class AnalystGrade(ProviderPayload):
    symbol: str
    date: Optional[date_type] = None
    grading_company: Optional[str] = None
    previous_grade: Optional[str] = None
    new_grade: Optional[str] = None
    action: Optional[str] = None


class PriceTarget(ProviderPayload):
    symbol: str
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    target_median: Optional[float] = None
    analyst_count: Optional[int] = None
    last_updated: Optional[datetime] = None


class MarketData(ProviderPayload):
    """Aggregate returned by MarketDataService.get_market_data:
    canonical bars + provenance + quality report (as dict — rehydrate with
    DataQualityReport.model_validate(md.quality))."""

    symbol: str
    interval: str = "1d"
    bars: List[OHLCVBar] = Field(default_factory=list)
    quality: Optional[Dict[str, Any]] = None
