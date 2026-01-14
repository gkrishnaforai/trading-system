"""
Alpha Vantage Provider Client
Implements all HTTP/SDK logic, rate limiting, retries, and response normalization
Follows the clean architecture pattern
"""
import logging
import time
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

import pandas as pd

from app.config import settings
from app.utils.rate_limiter import RateLimiter
from app.observability.logging import get_logger

logger = get_logger("alphavantage_client")

@dataclass
class AlphaVantageConfig:
    """Alpha Vantage configuration"""
    api_key: str
    base_url: str = "https://www.alphavantage.co/query"
    rate_limit_calls: int = 5  # Free tier: 5 calls/minute
    rate_limit_window: float = 60.0
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


class AlphaVantageClient:
    """
    Alpha Vantage provider client
    Owns all HTTP logic, rate limiting, retries, and response normalization
    """
    
    def __init__(self, config: AlphaVantageConfig):
        self.config = config
        self.session = requests.Session()
        self.session.timeout = config.timeout
        self.last_error: Optional[str] = None
        
        # Rate limiting for Alpha Vantage free tier
        self.rate_limiter = RateLimiter(
            max_calls=config.rate_limit_calls,
            time_window=config.rate_limit_window,
            name="AlphaVantage"
        )
        
        logger.info(f"✅ Alpha Vantage Client initialized (rate limit: {config.rate_limit_calls}/{config.rate_limit_window}s)")
    
    @classmethod
    def from_settings(cls, api_key: Optional[str] = None) -> "AlphaVantageClient":
        """Create client from settings"""
        resolved_key = api_key or settings.alphavantage_api_key
        if not resolved_key:
            raise ValueError("Alpha Vantage API key is required")
        
        config = AlphaVantageConfig(api_key=resolved_key)
        return cls(config)
    
    def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make HTTP request with rate limiting, retries, and error handling
        """
        # Rate limiting
        if not self.rate_limiter.acquire():
            raise Exception("Rate limit exceeded - could not acquire permission for API call")
        
        # Add API key to params
        params["apikey"] = self.config.api_key
        
        for attempt in range(self.config.max_retries):
            try:
                response = self.session.get(self.config.base_url, params=params)
                response.raise_for_status()
                
                data = response.json()
                
                # Check for Alpha Vantage API errors
                if "Error Message" in data:
                    raise ValueError(f"Alpha Vantage API error: {data['Error Message']}")
                
                if "Note" in data:
                    # Rate limit exceeded
                    logger.warning(f"Alpha Vantage rate limit exceeded: {data['Note']}")
                    if attempt < self.config.max_retries - 1:
                        time.sleep(self.config.retry_delay * (2 ** attempt))
                        continue
                
                return data
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{self.config.max_retries}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise
            except ValueError as e:
                # API error, don't retry
                raise
    
    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        """
        Fetch historical price data
        
        Args:
            symbol: Stock symbol
            **kwargs: Additional parameters (outputsize, datatype, etc.)
        
        Returns:
            DataFrame with OHLCV data
        """
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": kwargs.get("outputsize", "compact"),
            "datatype": "json"
        }
        
        data = self._make_request(params)
        
        # Parse time series data
        time_series_key = "Time Series (Daily)"
        if time_series_key not in data:
            raise ValueError(f"No time series data returned for {symbol}")
        
        time_series = data[time_series_key]
        
        # Convert to DataFrame
        records = []
        for date_str, values in time_series.items():
            records.append({
                "trade_date": pd.to_datetime(date_str).date(),
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
                "volume": int(values["5. volume"])
            })
        
        df = pd.DataFrame(records)
        df = df.sort_values("trade_date")
        df["stock_symbol"] = symbol
        
        logger.info(f"✅ Fetched {len(df)} price records for {symbol}")
        return df
    
    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch current price (intraday)
        Note: Requires paid Alpha Vantage subscription
        Returns dict with price and volume, or None if unavailable
        """
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": "1min",
            "outputsize": "compact"
        }
        
        try:
            data = self._make_request(params)
            time_series_key = f"Time Series (1min)"
            
            if time_series_key not in data:
                logger.warning(f"No intraday data available for {symbol}")
                return None
            
            # Get the most recent price
            time_series = data[time_series_key]
            latest_timestamp = sorted(time_series.keys())[-1]
            latest_data = time_series[latest_timestamp]
            
            return {
                "price": float(latest_data["4. close"]),
                "volume": int(latest_data["5. volume"]) if latest_data.get("5. volume") else None,
                "source": "alphavantage"
            }
            
        except Exception as e:
            logger.warning(f"Failed to fetch current price for {symbol}: {e}")
            return None
    
    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch symbol details and company information
        """
        params = {
            "function": "OVERVIEW",
            "symbol": symbol
        }
        
        data = self._make_request(params)
        
        if not data or "Symbol" not in data:
            raise ValueError(f"No overview data available for {symbol}")
        
        # Normalize response
        return {
            "symbol": data.get("Symbol", symbol),
            "name": data.get("Name", ""),
            "sector": data.get("Sector", ""),
            "industry": data.get("Industry", ""),
            "market_cap": int(data.get("MarketCapitalization", 0)) if data.get("MarketCapitalization") else None,
            "pe_ratio": float(data.get("PERatio", 0)) if data.get("PERRatio") and data["PERatio"] != "None" else None,
            "pb_ratio": float(data.get("PriceToBookRatio", 0)) if data.get("PriceToBookRatio") and data["PriceToBookRatio"] != "None" else None,
            "eps": float(data.get("EPS", 0)) if data.get("EPS") and data["EPS"] != "None" else None,
            "dividend_yield": float(data.get("DividendYield", 0)) if data.get("DividendYield") and data["DividendYield"] != "None" else None,
            "beta": float(data.get("Beta", 0)) if data.get("Beta") and data["Beta"] != "None" else None,
            "description": data.get("Description", ""),
            "country": data.get("Country", ""),
            "currency": data.get("Currency", "USD"),
            "exchange": data.get("Exchange", ""),
            "fifty_two_week_high": float(data.get("52WeekHigh", 0)) if data.get("52WeekHigh") and data["52WeekHigh"] != "None" else None,
            "fifty_two_week_low": float(data.get("52WeekLow", 0)) if data.get("52WeekLow") and data["52WeekLow"] != "None" else None,
        }
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamental financial data
        """
        # Alpha Vantage provides fundamentals through OVERVIEW and other functions
        overview = self.fetch_symbol_details(symbol)
        
        # Try to get additional financial statements
        try:
            # Income Statement
            params = {
                "function": "INCOME_STATEMENT",
                "symbol": symbol
            }
            income_data = self._make_request(params)
            
            # Get most recent annual data
            annual_reports = income_data.get("annualReports", [])
            if annual_reports:
                latest = annual_reports[0]
                overview.update({
                    "revenue": float(latest.get("totalRevenue", 0)),
                    "gross_profit": float(latest.get("grossProfit", 0)),
                    "operating_income": float(latest.get("operatingIncome", 0)),
                    "net_income": float(latest.get("netIncome", 0)),
                    "fiscal_date_ending": latest.get("fiscalDateEnding"),
                })
        except Exception as e:
            logger.warning(f"Failed to fetch income statement for {symbol}: {e}")
        
        return overview
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch recent news articles
        Note: Alpha Vantage news endpoint is deprecated, returning empty list
        """
        # Alpha Vantage news endpoint was deprecated
        # This is a placeholder that returns empty list
        logger.warning("Alpha Vantage news endpoint is deprecated")
        return []
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Fetch earnings data
        """
        params = {
            "function": "EARNINGS",
            "symbol": symbol
        }
        
        data = self._make_request(params)
        
        earnings = []
        
        # Process quarterly earnings
        quarterly_earnings = data.get("quarterlyEarnings", [])
        for report in quarterly_earnings[:20]:  # Limit to last 20 quarters
            earnings.append({
                "symbol": symbol,
                "fiscal_date_ending": report.get("fiscalDateEnding"),
                "report_date": report.get("reportedDate"),
                "eps_actual": float(report.get("reportedEPS", 0)) if report.get("reportedEPS") else None,
                "eps_estimate": float(report.get("estimatedEPS", 0)) if report.get("estimatedEPS") else None,
                "surprise": float(report.get("surprise", 0)) if report.get("surprise") else None,
                "surprise_percent": float(report.get("surprisePercentage", 0)) if report.get("surprisePercentage") else None,
            })
        
        logger.info(f"✅ Fetched {len(earnings)} earnings records for {symbol}")
        return earnings
    
    def fetch_technical_indicators(self, symbol: str, indicator_type: str = "SMA", **kwargs) -> Dict[str, Any]:
        """
        Fetch technical indicators
        """
        # Map indicator types to Alpha Vantage functions
        function_map = {
            "SMA": "SMA",
            "EMA": "EMA", 
            "RSI": "RSI",
            "MACD": "MACD",
            "BB": "BBANDS",
            "ADX": "ADX",
            "CCI": "CCI",
            "STOCH": "STOCH",
            "ATR": "ATR"
        }
        
        function = function_map.get(indicator_type.upper(), "SMA")
        
        params = {
            "function": function,
            "symbol": symbol,
            "interval": kwargs.get("interval", "daily"),
            "time_period": kwargs.get("time_period", 20),
            "series_type": kwargs.get("series_type", "close")
        }
        
        # Add specific parameters for different indicators
        if indicator_type.upper() == "MACD":
            params.update({
                "fastperiod": kwargs.get("fastperiod", 12),
                "slowperiod": kwargs.get("slowperiod", 26),
                "signalperiod": kwargs.get("signalperiod", 9)
            })
        elif indicator_type.upper() == "BB":
            params.update({
                "nbdevup": kwargs.get("nbdevup", 2),
                "nbdevdn": kwargs.get("nbdevdn", 2),
                "matype": kwargs.get("matype", 0)
            })
        elif indicator_type.upper() == "STOCH":
            params.update({
                "fastkperiod": kwargs.get("fastkperiod", 5),
                "slowkperiod": kwargs.get("slowkperiod", 3),
                "slowdperiod": kwargs.get("slowdperiod", 3)
            })
        
        data = self._make_request(params)
        
        # Parse technical indicator data
        result = {"symbol": symbol, "indicator_type": indicator_type}
        
        # Find the data key (varies by indicator type)
        data_key = None
        for key in data.keys():
            if "Technical Analysis" in key or key.startswith(function):
                data_key = key
                break
        
        if not data_key:
            raise ValueError(f"No technical indicator data returned for {symbol}")
        
        # Get the most recent value
        indicator_data = data[data_key]
        if indicator_data:
            latest_timestamp = sorted(indicator_data.keys())[-1]
            latest_values = indicator_data[latest_timestamp]
            
            result.update(latest_values)
        
        logger.info(f"✅ Fetched {indicator_type} for {symbol}")
        return result
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch industry peers information
        Note: Alpha Vantage doesn't have a direct industry peers endpoint
        Returns symbol overview as fallback
        """
        try:
            overview = self.fetch_symbol_details(symbol)
            return {
                "symbol": symbol,
                "industry": overview.get("industry", ""),
                "sector": overview.get("sector", ""),
                "peers": []  # Alpha Vantage doesn't provide peers
            }
        except Exception as e:
            logger.warning(f"Failed to fetch industry peers for {symbol}: {e}")
            return {"symbol": symbol, "peers": []}
    
    def is_available(self) -> bool:
        """
        Check if Alpha Vantage service is available
        """
        try:
            logger.debug(f"🔍 Testing Alpha Vantage API availability...")

            params = {
                "function": "OVERVIEW",
                "symbol": "AAPL",
            }

            logger.debug(f"📤 Making test request to Alpha Vantage API...")
            data = self._make_request(params)
            logger.debug(
                f"📥 Received response: {list(data.keys()) if isinstance(data, dict) else type(data)}"
            )

            if isinstance(data, dict) and ("Information" in data or "Note" in data):
                info = data.get("Information") or data.get("Note")
                self.last_error = f"Alpha Vantage throttled/notice response: {info}"
                logger.warning(self.last_error)
                return False

            is_available = isinstance(data, dict) and ("Symbol" in data)
            logger.debug(f"✅ API availability check result: {is_available}")
            self.last_error = None if is_available else "Alpha Vantage returned unexpected response"
            return is_available

        except Exception as e:
            self.last_error = f"Alpha Vantage service unavailable: {type(e).__name__}: {str(e)}"
            logger.error(self.last_error)
            return False
