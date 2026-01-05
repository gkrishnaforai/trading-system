"""
Data Validation Module
Comprehensive data quality checks for financial market data
Critical for ensuring accurate calculations and signals
"""
# Import validator first (defines types before importing checks)
# This is safe because validator imports checks lazily in __init__
from app.data_validation.validator import (
    DataValidator,
    ValidationResult,
    ValidationReport,
    ValidationSeverity,
    ValidationIssue
)

# Import checks (they import types from validator, which are already defined)
from app.data_validation.checks import (
    DataQualityCheck,
    MissingValuesCheck,
    DuplicateCheck,
    OutlierCheck,
    DataTypeCheck,
    RangeCheck,
    ContinuityCheck,
    VolumeCheck,
    IndicatorDataCheck
)

# Import specialized validators
from app.data_validation.fundamentals_validator import FundamentalsValidator
from app.data_validation.technical_indicators_validator import TechnicalIndicatorsValidator
from app.data_validation.earnings_data_validator import EarningsDataValidator
from app.data_validation.market_news_validator import MarketNewsValidator

__all__ = [
    'DataValidator',
    'ValidationResult',
    'ValidationReport',
    'ValidationSeverity',
    'ValidationIssue',
    'DataQualityCheck',
    'MissingValuesCheck',
    'DuplicateCheck',
    'OutlierCheck',
    'DataTypeCheck',
    'RangeCheck',
    'ContinuityCheck',
    'VolumeCheck',
    'IndicatorDataCheck',
    'FundamentalsValidator',
    'TechnicalIndicatorsValidator',
    'EarningsDataValidator',
    'MarketNewsValidator'
]

