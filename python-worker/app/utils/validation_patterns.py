"""
Common Validation Patterns
DRY: Centralizes repeated validation logic
"""
from typing import Any, Optional, List, Dict
from app.exceptions import ValidationError
from app.utils.validation import validate_symbol


def validate_symbol_param(symbol: str, param_name: str = "symbol") -> str:
    """
    Validate symbol parameter and return uppercase
    
    Args:
        symbol: Stock symbol to validate
        param_name: Parameter name for error messages
    
    Returns:
        Uppercase symbol
    
    Raises:
        ValidationError: If symbol is invalid
    """
    if not symbol:
        raise ValidationError(f"{param_name} is required", details={param_name: symbol})
    
    if not validate_symbol(symbol):
        raise ValidationError(f"Invalid {param_name}: {symbol}", details={param_name: symbol})
    
    return symbol.upper()


def validate_symbols_list(symbols: List[str], max_count: Optional[int] = None) -> List[str]:
    """
    Validate list of symbols
    
    Args:
        symbols: List of stock symbols
        max_count: Optional maximum number of symbols
    
    Returns:
        List of uppercase validated symbols
    
    Raises:
        ValidationError: If validation fails
    """
    if not symbols:
        raise ValidationError("At least one symbol is required", details={'symbols': symbols})
    
    if not isinstance(symbols, list):
        raise ValidationError("Symbols must be a list", details={'symbols': type(symbols).__name__})
    
    if max_count and len(symbols) > max_count:
        raise ValidationError(
            f"Maximum {max_count} symbols allowed, got {len(symbols)}",
            details={'symbols_count': len(symbols), 'max_count': max_count}
        )
    
    validated_symbols = []
    for symbol in symbols:
        validated_symbols.append(validate_symbol_param(symbol))
    
    return validated_symbols


def validate_date_range(
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    allow_future: bool = False
) -> tuple:
    """
    Validate date range parameters
    
    Args:
        start_date: Start date
        end_date: End date
        allow_future: Whether to allow future dates
    
    Returns:
        Tuple of (start_date, end_date) as datetime objects
    
    Raises:
        ValidationError: If validation fails
    """
    from datetime import datetime, date
    
    if start_date:
        if isinstance(start_date, str):
            try:
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(f"Invalid start_date format: {start_date}")
        elif isinstance(start_date, date):
            start_date = datetime.combine(start_date, datetime.min.time())
    
    if end_date:
        if isinstance(end_date, str):
            try:
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                raise ValidationError(f"Invalid end_date format: {end_date}")
        elif isinstance(end_date, date):
            end_date = datetime.combine(end_date, datetime.min.time())
    
    if start_date and end_date and start_date > end_date:
        raise ValidationError(
            "start_date must be before end_date",
            details={'start_date': str(start_date), 'end_date': str(end_date)}
        )
    
    if not allow_future:
        now = datetime.now()
        if start_date and start_date > now:
            raise ValidationError("start_date cannot be in the future")
        if end_date and end_date > now:
            raise ValidationError("end_date cannot be in the future")
    
    return start_date, end_date


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> None:
    """
    Validate that required fields are present in data dictionary
    
    Args:
        data: Data dictionary to validate
        required_fields: List of required field names
    
    Raises:
        ValidationError: If any required field is missing
    """
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    
    if missing_fields:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing_fields)}",
            details={'missing_fields': missing_fields, 'required_fields': required_fields}
        )


def validate_numeric_range(
    value: Any,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    param_name: str = "value"
) -> float:
    """
    Validate numeric value is within range
    
    Args:
        value: Value to validate
        min_value: Optional minimum value
        max_value: Optional maximum value
        param_name: Parameter name for error messages
    
    Returns:
        Validated float value
    
    Raises:
        ValidationError: If validation fails
    """
    try:
        float_value = float(value)
    except (ValueError, TypeError):
        raise ValidationError(
            f"{param_name} must be a number",
            details={param_name: value, 'type': type(value).__name__}
        )
    
    if min_value is not None and float_value < min_value:
        raise ValidationError(
            f"{param_name} must be >= {min_value}",
            details={param_name: float_value, 'min_value': min_value}
        )
    
    if max_value is not None and float_value > max_value:
        raise ValidationError(
            f"{param_name} must be <= {max_value}",
            details={param_name: float_value, 'max_value': max_value}
        )
    
    return float_value


def validate_period(period: str) -> str:
    """
    Validate period string for data fetching
    
    Args:
        period: Period string (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
    
    Returns:
        Validated period string
    
    Raises:
        ValidationError: If period is invalid
    """
    valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
    
    if period not in valid_periods:
        raise ValidationError(
            f"Invalid period: {period}. Valid periods: {', '.join(valid_periods)}",
            details={'period': period, 'valid_periods': valid_periods}
        )
    
    return period

