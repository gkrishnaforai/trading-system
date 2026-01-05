"""
Validation utilities
DRY: Centralize validation logic
"""
import logging
from typing import Dict, Any, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


def validate_symbol(symbol: str) -> bool:
    """
    Validate stock symbol
    
    Args:
        symbol: Stock symbol to validate
    
    Returns:
        True if valid
    """
    if not symbol or not isinstance(symbol, str):
        return False
    
    symbol = symbol.strip().upper()
    
    # Basic validation:
    # - allow macro/index tickers like ^VIX, ^TNX
    # - allow common Yahoo separators like '-', '.', '='
    if not (1 <= len(symbol) <= 12):
        return False
    
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789^.-=")
    if any(ch not in allowed for ch in symbol):
        return False
    
    return True


def validate_indicators(
    indicators: Dict[str, Any],
    required: Optional[List[str]] = None
) -> tuple[bool, Optional[str]]:
    """
    Validate indicators dictionary
    
    Args:
        indicators: Dictionary of indicators
        required: List of required indicator keys
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(indicators, dict):
        return False, "Indicators must be a dictionary"
    
    if required:
        missing = [key for key in required if key not in indicators]
        if missing:
            return False, f"Missing required indicators: {', '.join(missing)}"
    
    return True, None

