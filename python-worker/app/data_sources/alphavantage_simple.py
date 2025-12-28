"""Legacy Alpha Vantage helpers (kept for backward compatibility).

Architecture compliance: networking/rate limiting lives in the provider client.
This module delegates to app/providers/alphavantage/client.py.
"""

from typing import Dict, Any, Optional, List

from app.observability.logging import get_logger
from app.providers.alphavantage.client import AlphaVantageClient

logger = get_logger("alphavantage_simple")


class SimpleAlphaVantageSource:
    """Compatibility wrapper around AlphaVantageClient."""

    def __init__(self, api_key: str):
        self._client = AlphaVantageClient.from_settings(api_key=api_key)
        logger.info("✅ Simple Alpha Vantage wrapper initialized")
    
    def fetch_company_overview(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch company overview - exact same as the example"""
        try:
            details = self._client.fetch_symbol_details(symbol)
            return details if details else None
        except Exception as e:
            logger.error(f"Error fetching overview for {symbol}: {e}")
            return None
    
    def fetch_time_series_daily(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch daily time series"""
        try:
            # Return a dict-like payload for compatibility.
            df = self._client.fetch_price_data(symbol, outputsize="compact")
            if df is None or df.empty:
                return None
            return {"rows": df.to_dict(orient="records")}
        except Exception as e:
            logger.error(f"Error fetching time series for {symbol}: {e}")
            return None
    
    def fetch_technical_indicator(self, symbol: str, function: str, time_period: int = 14) -> Optional[Dict[str, Any]]:
        """Legacy helper: fetch one technical indicator via provider client."""
        try:
            return self._client.fetch_technical_indicators(
                symbol,
                indicator_type=function,
                time_period=time_period,
                interval="daily",
            )
        except Exception as e:
            logger.error(f"Error fetching {function} for {symbol}: {e}")
            return None
    
    def fetch_income_statement(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Legacy helper: return best-effort fundamentals payload."""
        try:
            return self._client.fetch_fundamentals(symbol)
        except Exception as e:
            logger.error(f"Error fetching income statement for {symbol}: {e}")
            return None
    
    def fetch_balance_sheet(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Legacy helper: return best-effort fundamentals payload."""
        try:
            return self._client.fetch_fundamentals(symbol)
        except Exception as e:
            logger.error(f"Error fetching balance sheet for {symbol}: {e}")
            return None
    
    def fetch_cash_flow(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Legacy helper: return best-effort fundamentals payload."""
        try:
            return self._client.fetch_fundamentals(symbol)
        except Exception as e:
            logger.error(f"Error fetching cash flow for {symbol}: {e}")
            return None
    
    def fetch_earnings(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Legacy helper: return list payload wrapped in a dict."""
        try:
            rows: List[Dict[str, Any]] = self._client.fetch_earnings(symbol)
            return {"rows": rows}
        except Exception as e:
            logger.error(f"Error fetching earnings for {symbol}: {e}")
            return None
