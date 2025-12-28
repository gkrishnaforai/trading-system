"""
Indicator Keys Constants and Normalization
Canonical names used across the entire application (repos, services, strategies, Streamlit)
to avoid column name mismatches.
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical indicator key names (used by strategies, UI, and services)
# ---------------------------------------------------------------------------
class IndicatorKeys:
    """Canonical indicator key constants"""
    # Moving averages
    SMA_50 = "sma50"
    SMA_200 = "sma200"
    EMA_20 = "ema20"
    EMA_50 = "ema50"  # Derived from EMA_20 as fallback
    
    # Momentum
    RSI_14 = "rsi"
    MACD_LINE = "macd_line"
    MACD_SIGNAL = "macd_signal"
    MACD_HIST = "macd_hist"
    
    # Price/volume
    PRICE = "price"
    VOLUME = "volume"
    VOLUME_MA = "volume_ma"
    
    # Trend
    LONG_TERM_TREND = "long_term_trend"
    MEDIUM_TERM_TREND = "medium_term_trend"
    
    # Signal
    SIGNAL = "signal"
    CONFIDENCE_SCORE = "confidence_score"

# ---------------------------------------------------------------------------
# Fundamental key constants
# ---------------------------------------------------------------------------
class FundamentalKeys:
    """Canonical fundamental key constants"""
    PE_RATIO = "pe_ratio"
    PB_RATIO = "pb_ratio"
    PRICE_TO_SALES = "price_to_sales"
    DEBT_TO_EQUITY = "debt_to_equity"
    TOTAL_DEBT = "total_debt"
    LONG_TERM_DEBT = "long_term_debt"
    SHORT_TERM_DEBT = "short_term_debt"
    TOTAL_EQUITY = "total_equity"
    ROE = "roe"
    REVENUE_GROWTH = "revenue_growth"
    MARKET_CAP = "market_cap"
    DIVIDEND_YIELD = "dividend_yield"
    EPS = "eps"
    BOOK_VALUE = "book_value"
    SECTOR = "sector"
    INDUSTRY = "industry"

# ---------------------------------------------------------------------------
# Helper: Get all required indicator keys (used by validation)
# ---------------------------------------------------------------------------
def get_required_indicator_keys() -> List[str]:
    """Get list of all required indicator keys for strategies"""
    return [
        IndicatorKeys.PRICE,
        IndicatorKeys.EMA_20,
        IndicatorKeys.EMA_50,
        IndicatorKeys.SMA_200,
        IndicatorKeys.MACD_LINE,
        IndicatorKeys.MACD_SIGNAL,
        IndicatorKeys.RSI_14,
    ]

def get_all_indicator_keys() -> List[str]:
    """Get list of all known indicator keys"""
    return [
        IndicatorKeys.SMA_50,
        IndicatorKeys.SMA_200,
        IndicatorKeys.EMA_20,
        IndicatorKeys.EMA_50,
        IndicatorKeys.RSI_14,
        IndicatorKeys.MACD_LINE,
        IndicatorKeys.MACD_SIGNAL,
        IndicatorKeys.MACD_HIST,
        IndicatorKeys.PRICE,
        IndicatorKeys.VOLUME,
        IndicatorKeys.VOLUME_MA,
        IndicatorKeys.LONG_TERM_TREND,
        IndicatorKeys.MEDIUM_TERM_TREND,
        IndicatorKeys.SIGNAL,
        IndicatorKeys.CONFIDENCE_SCORE,
    ]

def get_required_fundamental_keys() -> List[str]:
    """Get list of all required fundamental keys"""
    return [
        FundamentalKeys.PE_RATIO,
        FundamentalKeys.PB_RATIO,
        FundamentalKeys.PRICE_TO_SALES,
        FundamentalKeys.DEBT_TO_EQUITY,
        FundamentalKeys.ROE,
        FundamentalKeys.REVENUE_GROWTH,
    ]

def get_all_fundamental_keys() -> List[str]:
    """Get list of all known fundamental keys"""
    return [
        FundamentalKeys.PE_RATIO,
        FundamentalKeys.PB_RATIO,
        FundamentalKeys.PRICE_TO_SALES,
        FundamentalKeys.DEBT_TO_EQUITY,
        FundamentalKeys.ROE,
        FundamentalKeys.REVENUE_GROWTH,
        FundamentalKeys.MARKET_CAP,
        FundamentalKeys.DIVIDEND_YIELD,
        FundamentalKeys.EPS,
        FundamentalKeys.BOOK_VALUE,
        FundamentalKeys.SECTOR,
        FundamentalKeys.INDUSTRY,
    ]

# ---------------------------------------------------------------------------
# Normalization: Convert any indicator dict to canonical keys
# ---------------------------------------------------------------------------
def normalize_indicator_keys(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert indicator dict with any naming scheme to canonical keys.
    
    Handles:
    - Raw DB names: sma_50, ema_20, rsi_14, macd, macd_hist
    - Aliased names: sma50, ema20, rsi, macd_line, macd_hist
    - Legacy names: any other variants
    
    Args:
        indicators: Dictionary with indicator values (any key naming scheme)
        
    Returns:
        Dictionary with canonical keys only
    """
    if not indicators:
        return {}
    
    # Mapping from all possible variants to canonical keys
    variant_to_canonical = {
        # Raw DB names
        "sma_50": IndicatorKeys.SMA_50,
        "sma_200": IndicatorKeys.SMA_200,
        "ema_20": IndicatorKeys.EMA_20,
        "rsi_14": IndicatorKeys.RSI_14,
        "macd": IndicatorKeys.MACD_LINE,
        "macd_signal": IndicatorKeys.MACD_SIGNAL,
        "macd_hist": IndicatorKeys.MACD_HIST,
        
        # Aliased names (already canonical)
        "sma50": IndicatorKeys.SMA_50,
        "sma200": IndicatorKeys.SMA_200,
        "ema20": IndicatorKeys.EMA_20,
        "rsi": IndicatorKeys.RSI_14,
        "macd_line": IndicatorKeys.MACD_LINE,
        "macd_hist": IndicatorKeys.MACD_HIST,
        
        # Other possible variants
        "sma50": IndicatorKeys.SMA_50,
        "sma200": IndicatorKeys.SMA_200,
        "ema20": IndicatorKeys.EMA_20,
        "rsi14": IndicatorKeys.RSI_14,
        "macd_histogram": IndicatorKeys.MACD_HIST,
        
        # Price/volume
        "close": IndicatorKeys.PRICE,
        "price": IndicatorKeys.PRICE,
        "volume": IndicatorKeys.VOLUME,
        "volume_ma": IndicatorKeys.VOLUME_MA,
    }
    
    normalized = {}
    
    for key, value in indicators.items():
        if value is None:
            continue
            
        # Convert key to canonical
        canonical_key = variant_to_canonical.get(key.lower(), key.lower())
        
        # Only keep known canonical keys
        if canonical_key in get_all_indicator_keys():
            # Clean numeric values
            if isinstance(value, (int, float)):
                normalized[canonical_key] = float(value)
            else:
                normalized[canonical_key] = value
    
    # Special case: derive ema50 from ema20 if missing
    if IndicatorKeys.EMA_50 not in normalized and IndicatorKeys.EMA_20 in normalized:
        normalized[IndicatorKeys.EMA_50] = normalized[IndicatorKeys.EMA_20]
        logger.debug("Derived ema50 from ema20 as fallback")
    
    return normalized

def normalize_fundamental_keys(fundamentals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert fundamental dict with any naming scheme to canonical keys.
    
    Args:
        fundamentals: Dictionary with fundamental values (any key naming scheme)
        
    Returns:
        Dictionary with canonical keys only
    """
    if not fundamentals:
        return {}
    
    # Mapping from variants to canonical keys
    variant_to_canonical = {
        # Common variants
        "pe_ratio": FundamentalKeys.PE_RATIO,
        "pe": FundamentalKeys.PE_RATIO,
        "price_to_earnings": FundamentalKeys.PE_RATIO,
        
        "pb_ratio": FundamentalKeys.PB_RATIO,
        "pb": FundamentalKeys.PB_RATIO,
        "price_to_book": FundamentalKeys.PB_RATIO,
        
        "price_to_sales": FundamentalKeys.PRICE_TO_SALES,
        "ps": FundamentalKeys.PRICE_TO_SALES,
        
        "debt_to_equity": FundamentalKeys.DEBT_TO_EQUITY,
        "debt_equity": FundamentalKeys.DEBT_TO_EQUITY,
        
        "total_debt": FundamentalKeys.TOTAL_DEBT,
        "long_term_debt": FundamentalKeys.LONG_TERM_DEBT,
        "short_term_debt": FundamentalKeys.SHORT_TERM_DEBT,
        "total_equity": FundamentalKeys.TOTAL_EQUITY,
        
        "roe": FundamentalKeys.ROE,
        "return_on_equity": FundamentalKeys.ROE,
        
        "revenue_growth": FundamentalKeys.REVENUE_GROWTH,
        "revenue_growth_rate": FundamentalKeys.REVENUE_GROWTH,
        
        "market_cap": FundamentalKeys.MARKET_CAP,
        "market_capitalization": FundamentalKeys.MARKET_CAP,
        
        "dividend_yield": FundamentalKeys.DIVIDEND_YIELD,
        "dividend": FundamentalKeys.DIVIDEND_YIELD,
        
        "eps": FundamentalKeys.EPS,
        "earnings_per_share": FundamentalKeys.EPS,
        
        "book_value": FundamentalKeys.BOOK_VALUE,
        "book_value_per_share": FundamentalKeys.BOOK_VALUE,
        
        "sector": FundamentalKeys.SECTOR,
        "industry": FundamentalKeys.INDUSTRY,
        "industry_key": FundamentalKeys.INDUSTRY,
    }
    
    normalized = {}
    
    for key, value in fundamentals.items():
        if value is None:
            continue
            
        # Convert key to canonical
        canonical_key = variant_to_canonical.get(key.lower(), key.lower())
        
        # Only keep known canonical keys
        if canonical_key in get_all_fundamental_keys():
            # Clean numeric values
            if isinstance(value, (int, float)):
                normalized[canonical_key] = float(value)
            else:
                normalized[canonical_key] = value
    
    return normalized

# ---------------------------------------------------------------------------
# Validation helpers using canonical keys
# ---------------------------------------------------------------------------
def get_missing_indicators(indicators: Dict[str, Any]) -> List[str]:
    """Get list of missing required indicators using canonical keys"""
    required = get_required_indicator_keys()
    missing = [key for key in required if key not in indicators or indicators[key] is None]
    return missing

def get_missing_fundamentals(fundamentals: Dict[str, Any]) -> List[str]:
    """Get list of missing required fundamentals using canonical keys"""
    required = get_required_fundamental_keys()
    missing = [key for key in required if key not in fundamentals or fundamentals[key] is None]
    return missing
