"""
Market data layer — canonical models + provider routing + data quality.

    MarketDataService          <- facade for quant/agent layers
          |
    ProviderRouter             <- ordered fallback chain per capability
          |
      FMP / Yahoo / Massive    <- thin adapters over existing clients
          |
    normalize_bars             <- canonical price policy (policy.py)
          |
    validate_bars              <- data-quality report (validation.py)

Contract: providers raise DataNotFound / ProviderError / UnsupportedCapability
instead of returning ambiguous empty results. Router falls back per route
config (MARKET_DATA_ROUTES env or primary/fallback settings).
"""
from . import indicators
from .base import CAPABILITIES, MarketDataProvider
from .errors import (
    DataNotFound,
    DataQualityError,
    MarketDataUnavailable,
    ProviderAttempt,
    ProviderError,
    UnsupportedCapability,
)
from .models import (
    AnalystGrade,
    CompanyProfile,
    EarningsEvent,
    FinancialStatements,
    FundamentalsSnapshot,
    MarketData,
    NewsItem,
    OHLCVBar,
    PriceTarget,
    Quote,
)
from .policy import CANONICAL_PRICE_POLICY, PricePolicy, normalize_bars
from .router import ProviderRouter
from .service import MarketDataService, get_market_data_service
from .validation import (
    DataQualityIssue,
    DataQualityReport,
    IssueSeverity,
    validate_bars,
)

__all__ = [
    "CAPABILITIES",
    "MarketDataProvider",
    "ProviderRouter",
    "MarketDataService",
    "get_market_data_service",
    "ProviderError",
    "DataNotFound",
    "UnsupportedCapability",
    "MarketDataUnavailable",
    "DataQualityError",
    "ProviderAttempt",
    "OHLCVBar",
    "Quote",
    "CompanyProfile",
    "FundamentalsSnapshot",
    "FinancialStatements",
    "NewsItem",
    "EarningsEvent",
    "AnalystGrade",
    "PriceTarget",
    "MarketData",
    "PricePolicy",
    "CANONICAL_PRICE_POLICY",
    "normalize_bars",
    "validate_bars",
    "DataQualityIssue",
    "DataQualityReport",
    "IssueSeverity",
]
