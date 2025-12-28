"""
Utility functions for common operations
DRY principle: Centralize repeated code patterns
"""
from app.utils.series_utils import extract_latest_value, extract_latest_values
from app.utils.validation import validate_symbol, validate_indicators
from app.utils.database_helper import DatabaseQueryHelper
from app.utils.exception_handler import (
    handle_exceptions,
    handle_database_errors,
    handle_validation_errors
)
from app.utils.validation_patterns import (
    validate_symbol_param,
    validate_symbols_list,
    validate_date_range,
    validate_required_fields,
    validate_numeric_range,
    validate_period
)

__all__ = [
    'extract_latest_value',
    'extract_latest_values',
    'validate_symbol',
    'validate_indicators',
    'DatabaseQueryHelper',
    'handle_exceptions',
    'handle_database_errors',
    'handle_validation_errors',
    'validate_symbol_param',
    'validate_symbols_list',
    'validate_date_range',
    'validate_required_fields',
    'validate_numeric_range',
    'validate_period',
]

