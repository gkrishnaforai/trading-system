"""
Utilities for working with pandas Series
DRY: Centralize Series value extraction patterns
"""
import pandas as pd
from typing import Any, Optional, Dict, List, Union


def extract_latest_value(series: Union[pd.Series, Any], default: Any = None) -> Any:
    """
    Extract latest value from pandas Series or return value as-is
    
    Args:
        series: pandas Series or any value
        default: Default value if Series is empty or value is None
    
    Returns:
        Latest value from Series or the value itself if not a Series
    """
    if isinstance(series, pd.Series):
        if len(series) > 0:
            value = series.iloc[-1]
            if pd.notna(value):
                return value
    elif series is not None:
        return series
    
    return default


def extract_latest_values(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract latest values from a dictionary of indicators (may contain Series)
    
    Args:
        indicators: Dictionary where values may be pandas Series
    
    Returns:
        Dictionary with latest values extracted
    """
    result = {}
    for key, value in indicators.items():
        result[key] = extract_latest_value(value)
    return result

