"""
Financial Modeling Prep (FMP) Provider Client
Implements all HTTP/SDK logic, rate limiting, retries, and response normalization
Follows the clean architecture pattern
"""
import logging
import time
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import math

import pandas as pd

from app.config import settings
from app.utils.rate_limiter import RateLimiter
from app.observability.logging import get_logger

logger = get_logger("fmp_client")

@dataclass
class FinancialModelingPrepConfig:
    """Financial Modeling Prep configuration"""
    api_key: str
    base_url: str = "https://financialmodelingprep.com/stable"
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    rate_limit_calls: int = 60
    rate_limit_window: float = 60.0


class FinancialModelingPrepClient:
    """
    Financial Modeling Prep provider client
    Owns all HTTP logic, rate limiting, retries, and response normalization
    """
    
    def __init__(self, config: FinancialModelingPrepConfig):
        self.config = config
        self.session = requests.Session()
        self.session.timeout = config.timeout
        self.last_error: Optional[str] = None
        
        # Rate limiting for FMP
        self.rate_limiter = RateLimiter(
            max_calls=config.rate_limit_calls,
            time_window=config.rate_limit_window,
            name="FMP"
        )
        
        logger.info(f"✅ FMP Client initialized (rate limit: {config.rate_limit_calls}/{config.rate_limit_window}s)")
    
    @classmethod
    def from_settings(cls) -> "FinancialModelingPrepClient":
        """Create client with default settings"""
        config = FinancialModelingPrepConfig(
            api_key=settings.fmp_api_key,
            base_url=settings.fmp_base_url,
            timeout=settings.fmp_timeout,
            max_retries=settings.fmp_max_retries,
            retry_delay=settings.fmp_retry_delay,
            rate_limit_calls=settings.fmp_rate_limit_calls,
            rate_limit_window=settings.fmp_rate_limit_window
        )
        return cls(config)
    
    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make HTTP request with rate limiting, retries, and error handling
        """
        # Rate limiting
        if not self.rate_limiter.acquire():
            raise Exception("Rate limit exceeded - could not acquire permission for API call")
        
        # Add API key to params
        if params is None:
            params = {}
        params["apikey"] = self.config.api_key
        
        url = f"{self.config.base_url}{endpoint}"
        
        for attempt in range(self.config.max_retries):
            try:
                response = self.session.get(url, params=params, timeout=self.config.timeout)
                response.raise_for_status()
                
                data = response.json()
                
                # Check for FMP API errors
                if "Error Message" in data:
                    raise ValueError(f"FMP API error: {data['Error Message']}")
                
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
    
    def _to_jsonable(self, obj: Any) -> Any:
        """Convert objects to JSON-serializable format"""
        if obj is None:
            return None
        if isinstance(obj, (str, int, bool)):
            return obj
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        if isinstance(obj, (list, tuple, set)):
            return [self._to_jsonable(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): self._to_jsonable(v) for k, v in obj.items()}
        if isinstance(obj, pd.Series):
            return self._to_jsonable(obj.to_dict())
        if isinstance(obj, pd.DataFrame):
            return self._df_to_records(obj)
        if hasattr(obj, "item"):
            try:
                return self._to_jsonable(obj.item())
            except Exception:
                pass
        return str(obj)
    
    def _df_to_records(self, df: pd.DataFrame, limit: int = 50) -> List[Dict[str, Any]]:
        """Convert DataFrame to list of records"""
        if df is None or getattr(df, "empty", True):
            return []
        safe_df = df.copy()
        safe_df = safe_df.reset_index()
        safe_df = safe_df.head(limit)
        records = safe_df.to_dict(orient="records")
        return [self._to_jsonable(r) for r in records]
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert to int"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime"""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    
    # === Core Data Methods ===
    
    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        """
        Fetch historical price data
        
        Args:
            symbol: Stock symbol
            **kwargs: Additional parameters (period, interval, etc.)
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            # For historical data, we need to use v3 API as stable API doesn't have historical endpoints
            # So we'll use the v3 base URL specifically for historical data
            base_url = self.config.base_url
            if base_url.endswith("/stable"):
                # Temporarily switch to v3 API for historical data
                self.config.base_url = "https://financialmodelingprep.com/api/v3"
            
            try:
                # Determine endpoint based on interval
                interval = kwargs.get("interval", "1d")
                if interval == "1d":
                    # Daily historical data
                    endpoint = f"/historical-price-full/{symbol}"
                    params = {
                        "timeseries": kwargs.get("timeseries", 5000)  # Max for FMP
                    }
                elif interval == "15m":
                    # Intraday data (if available)
                    endpoint = f"/historical-chart/15min/{symbol}"
                    params = {}
                else:
                    logger.warning(f"Unsupported interval {interval} for FMP, falling back to daily")
                    endpoint = f"/historical-price-full/{symbol}"
                    params = {"timeseries": 5000}
                
                data = self._make_request(endpoint, params)
                
                if not data:
                    return pd.DataFrame()
                
                # Normalize to DataFrame
                if interval == "1d" and "historical" in data:
                    df = pd.DataFrame(data["historical"])
                elif interval != "1d":
                    df = pd.DataFrame(data)
                else:
                    return pd.DataFrame()
                
                if df.empty:
                    return pd.DataFrame()
                
                # Standardize column names
                column_map = {
                    "date": "date",
                    "open": "open",
                    "high": "high", 
                    "low": "low",
                    "close": "close",
                    "adjClose": "adj_close",
                    "volume": "volume"
                }
                
                df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})
                
                # Convert date column to datetime index
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                
                # Convert numeric columns
                numeric_cols = ["open", "high", "low", "close", "adj_close", "volume"]
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                
                return df
                
            finally:
                # Restore original base URL
                self.config.base_url = base_url
            
        except Exception as e:
            logger.error(f"Error fetching price data for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Fetch current/live price"""
        try:
            endpoint = "/quote"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if not data or not isinstance(data, list) or len(data) == 0:
                return None
            
            quote = data[0]
            return self._safe_float(quote.get("price"))
            
        except Exception as e:
            logger.error(f"Error fetching current price for {symbol}: {e}")
            return None
    
    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """Fetch symbol details"""
        try:
            endpoint = "/profile"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if not data or not isinstance(data, list) or len(data) == 0:
                return {}
            
            profile = data[0]
            return {
                "symbol": profile.get("symbol"),
                "companyName": profile.get("companyName"),
                "sector": profile.get("sector"),
                "industry": profile.get("industry"),
                "marketCap": self._safe_float(profile.get("marketCap")),
                "description": profile.get("description"),
                "website": profile.get("website"),
                "currency": profile.get("currency"),
                "country": profile.get("country"),
                "exchange": profile.get("exchange")
            }
            
        except Exception as e:
            logger.error(f"Error fetching symbol details for {symbol}: {e}")
            return {}
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data"""
        try:
            # Get profile for basic info
            profile = self.fetch_symbol_details(symbol)
            
            # Get key metrics
            endpoint = f"/v3/key-metrics-ttm/{symbol}"
            metrics_data = self._make_request(endpoint)
            metrics = metrics_data[0] if metrics_data and isinstance(metrics_data, list) else {}
            
            # Get ratios
            endpoint = f"/v3/ratios-ttm/{symbol}"
            ratios_data = self._make_request(endpoint)
            ratios = ratios_data[0] if ratios_data and isinstance(ratios_data, list) else {}
            
            # Combine into fundamentals dict
            fundamentals = {
                **profile,
                "peRatio": self._safe_float(metrics.get("peRatioTTM")),
                "pbRatio": self._safe_float(metrics.get("pbRatioTTM")),
                "psRatio": self._safe_float(metrics.get("psRatioTTM")),
                "roe": self._safe_float(metrics.get("roeTTM")),
                "debtToEquity": self._safe_float(metrics.get("debtToEquityTTM")),
                "currentRatio": self._safe_float(metrics.get("currentRatioTTM")),
                "grossProfitMargin": self._safe_float(metrics.get("grossProfitMarginTTM")),
                "operatingProfitMargin": self._safe_float(metrics.get("operatingProfitMarginTTM")),
                "netProfitMargin": self._safe_float(metrics.get("netProfitMarginTTM")),
                "revenuePerShare": self._safe_float(metrics.get("revenuePerShareTTM")),
                "eps": self._safe_float(metrics.get("epsTTM")),
                "bookValuePerShare": self._safe_float(metrics.get("bookValuePerShareTTM")),
                "marketCapPerShare": self._safe_float(metrics.get("marketCapPerShareTTM")),
            }
            
            return fundamentals
            
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return {}
    
    def fetch_enhanced_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch enhanced fundamentals with additional metrics"""
        return self.fetch_fundamentals(symbol)
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles"""
        try:
            endpoint = "/news/stock"
            params = {
                "symbols": symbol,
                "limit": limit
            }
            data = self._make_request(endpoint, params)
            
            if not data or not isinstance(data, list):
                return []
            
            news = []
            for article in data[:limit]:
                news.append({
                    "title": article.get("title"),
                    "publisher": article.get("source"),
                    "url": article.get("url"),
                    "published": article.get("publishedDate"),
                    "summary": article.get("text")
                })
            
            return news
            
        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch earnings data"""
        try:
            # Get earnings for specific symbol
            endpoint = "/earnings"
            params = {
                "symbol": symbol
            }
            data = self._make_request(endpoint, params)
            
            if not data or not isinstance(data, list):
                return []
            
            earnings = []
            for item in data:
                earnings.append({
                    "earnings_date": item.get("date"),
                    "earnings_at": None,  # FMP doesn't provide time
                    "earnings_timezone": "America/New_York",
                    "earnings_session": "unknown",
                    "eps_estimate": self._safe_float(item.get("epsEstimated")),
                    "eps_actual": self._safe_float(item.get("eps")),
                    "revenue_estimate": self._safe_float(item.get("revenueEstimated")),
                    "revenue_actual": self._safe_float(item.get("revenue")),
                    "surprise_percentage": None  # Calculate if needed
                })
            
            return earnings
            
        except Exception as e:
            logger.error(f"Error fetching earnings for {symbol}: {e}")
            return []
    
    def fetch_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """Fetch earnings calendar"""
        try:
            endpoint = "/earnings-calendar"
            params = {}
            
            # FMP stable API doesn't support symbol filtering for earnings calendar
            # It returns all earnings data
            
            data = self._make_request(endpoint, params)
            
            if not data or not isinstance(data, list):
                return []
            
            calendar = []
            for item in data:
                # Filter by symbols if provided
                if symbols:
                    if item.get("symbol") not in symbols:
                        continue
                
                # Filter by date range if provided
                if start_date or end_date:
                    item_date = item.get("date")
                    if item_date:
                        if start_date and item_date < start_date:
                            continue
                        if end_date and item_date > end_date:
                            continue
                
                calendar.append({
                    "symbol": item.get("symbol"),
                    "earnings_date": item.get("date"),
                    "eps_estimate": self._safe_float(item.get("epsEstimated")),
                    "eps_actual": self._safe_float(item.get("eps")),
                    "revenue_estimate": self._safe_float(item.get("revenueEstimated")),
                    "revenue_actual": self._safe_float(item.get("revenue"))
                })
            
            return calendar
            
        except Exception as e:
            logger.error(f"Error fetching earnings calendar: {e}")
            return []
    
    def fetch_earnings_for_date(self, earnings_date: str, symbols: List[str] = None) -> List[Dict[str, Any]]:
        """Fetch earnings for a specific date"""
        return self.fetch_earnings_calendar(symbols, earnings_date, earnings_date)
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Fetch industry peers"""
        try:
            # Get symbol details first
            profile = self.fetch_symbol_details(symbol)
            
            # FMP doesn't have a direct peers endpoint, so we'll return sector/industry info
            return {
                "sector": profile.get("sector"),
                "industry": profile.get("industry"),
                "peers": []  # Would need a separate API or database lookup
            }
            
        except Exception as e:
            logger.error(f"Error fetching industry peers for {symbol}: {e}")
            return {}
    
    def fetch_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch corporate actions (dividends and splits)"""
        try:
            # Get dividends
            dividends_endpoint = f"/v3/historical-price-full/stock_dividend/{symbol}"
            dividends_data = self._make_request(dividends_endpoint)
            
            # Get stock splits
            splits_endpoint = f"/v3/historical-price-full/stock_split/{symbol}"
            splits_data = self._make_request(splits_endpoint)
            
            actions = []
            
            # Process dividends
            if dividends_data and "historical" in dividends_data:
                for item in dividends_data["historical"]:
                    actions.append({
                        "date": item.get("date"),
                        "action": "dividend",
                        "amount": self._safe_float(item.get("dividend"))
                    })
            
            # Process splits
            if splits_data and "historical" in splits_data:
                for item in splits_data["historical"]:
                    actions.append({
                        "date": item.get("date"),
                        "action": "split",
                        "ratio": item.get("splitRatio")
                    })
            
            return actions
            
        except Exception as e:
            logger.error(f"Error fetching actions for {symbol}: {e}")
            return []
    
    def fetch_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch dividend history"""
        try:
            endpoint = f"/v3/historical-price-full/stock_dividend/{symbol}"
            data = self._make_request(endpoint)
            
            if not data or "historical" not in data:
                return []
            
            dividends = []
            for item in data["historical"]:
                dividends.append({
                    "date": item.get("date"),
                    "dividend": self._safe_float(item.get("dividend"))
                })
            
            return dividends
            
        except Exception as e:
            logger.error(f"Error fetching dividends for {symbol}: {e}")
            return []
    
    def fetch_splits(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch stock split history"""
        try:
            endpoint = f"/v3/historical-price-full/stock_split/{symbol}"
            data = self._make_request(endpoint)
            
            if not data or "historical" not in data:
                return []
            
            splits = []
            for item in data["historical"]:
                splits.append({
                    "date": item.get("date"),
                    "splitRatio": item.get("splitRatio")
                })
            
            return splits
            
        except Exception as e:
            logger.error(f"Error fetching splits for {symbol}: {e}")
            return []
    
    def fetch_financial_statements(self, symbol: str, *, quarterly: bool = True) -> Dict[str, Any]:
        """Fetch financial statements"""
        try:
            period = "quarter" if quarterly else "annual"
            
            # Income statement
            income_endpoint = f"/v3/income-statement/{symbol}?period={period}&limit=10"
            income_data = self._make_request(income_endpoint)
            
            # Balance sheet
            balance_endpoint = f"/v3/balance-sheet-statement/{symbol}?period={period}&limit=10"
            balance_data = self._make_request(balance_endpoint)
            
            # Cash flow
            cashflow_endpoint = f"/v3/cash-flow-statement/{symbol}?period={period}&limit=10"
            cashflow_data = self._make_request(cashflow_endpoint)
            
            return {
                "income_statement": income_data if isinstance(income_data, list) else [],
                "balance_sheet": balance_data if isinstance(balance_data, list) else [],
                "cash_flow": cashflow_data if isinstance(cashflow_data, list) else []
            }
            
        except Exception as e:
            logger.error(f"Error fetching financial statements for {symbol}: {e}")
            return {
                "income_statement": [],
                "balance_sheet": [],
                "cash_flow": []
            }
    
    def fetch_quarterly_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch quarterly earnings history"""
        try:
            endpoint = f"/v3/earnings-surprises/{symbol}"
            data = self._make_request(endpoint)
            
            if not data or not isinstance(data, list):
                return []
            
            earnings_history = []
            for item in data:
                earnings_history.append({
                    "date": item.get("date"),
                    "symbol": item.get("symbol"),
                    "actualEarningResult": self._safe_float(item.get("actualEarningResult")),
                    "estimatedEarningResult": self._safe_float(item.get("estimatedEarningResult")),
                    "surprise": self._safe_float(item.get("surprise")),
                    "surprisePercentage": self._safe_float(item.get("surprisePercentage"))
                })
            
            return earnings_history
            
        except Exception as e:
            logger.error(f"Error fetching quarterly earnings history for {symbol}: {e}")
            return []
    
    def fetch_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch analyst recommendations"""
        try:
            endpoint = f"/v3/grade/{symbol}"
            data = self._make_request(endpoint)
            
            if not data or not isinstance(data, list):
                return []
            
            recommendations = []
            for item in data:
                recommendations.append({
                    "date": item.get("date"),
                    "grade": item.get("grade"),
                    "gradingCompany": item.get("gradingCompany"),
                    "price": self._safe_float(item.get("price")),
                    "newGrade": item.get("newGrade"),
                    "previousGrade": item.get("previousGrade")
                })
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error fetching analyst recommendations for {symbol}: {e}")
            return []
    
    def is_available(self) -> bool:
        """Check if FMP service is available"""
        try:
            # Test with a simple profile request for AAPL using stable API
            endpoint = "/profile"
            params = {"symbol": "AAPL"}
            data = self._make_request(endpoint, params)
            return data is not None and isinstance(data, list) and len(data) > 0
        except Exception as e:
            logger.error(f"FMP availability check failed: {e}")
            self.last_error = str(e)
            return False
