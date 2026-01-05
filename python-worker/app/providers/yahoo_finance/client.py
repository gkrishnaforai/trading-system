"""
Yahoo Finance Provider Client
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
import yfinance as yf

from app.config import settings
from app.utils.rate_limiter import RateLimiter
from app.observability.logging import get_logger

logger = get_logger("yahoo_finance_client")

@dataclass
class YahooFinanceConfig:
    """Yahoo Finance configuration"""
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    rate_limit_calls: int = 100  # Conservative rate limit
    rate_limit_window: float = 60.0


class YahooFinanceClient:
    """
    Yahoo Finance provider client
    Owns all HTTP logic, rate limiting, retries, and response normalization
    """
    
    def __init__(self, config: YahooFinanceConfig):
        self.config = config
        self.session = requests.Session()
        # requests.Session doesn't have a reliable global timeout; pass timeout per request.

        # Suppress the noisy 404 error from fundamentals-timeseries endpoint
        # This endpoint fails for many symbols but doesn't affect core functionality
        logging.getLogger("yfinance").setLevel(logging.ERROR)
        
        # Rate limiting (conservative for Yahoo Finance)
        self.rate_limiter = RateLimiter(
            max_calls=config.rate_limit_calls,
            time_window=config.rate_limit_window,
            name="YahooFinance"
        )
        
        logger.info(f"✅ Yahoo Finance Client initialized (rate limit: {config.rate_limit_calls}/{config.rate_limit_window}s)")
    
    @classmethod
    def from_settings(cls) -> "YahooFinanceClient":
        """Create client with default settings"""
        config = YahooFinanceConfig()
        return cls(config)

    def _to_jsonable(self, obj: Any) -> Any:
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
        if df is None or getattr(df, "empty", True):
            return []

        safe_df = df.copy()
        safe_df = safe_df.reset_index()
        safe_df = safe_df.head(limit)
        records = safe_df.to_dict(orient="records")
        return [self._to_jsonable(r) for r in records]
    
    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """
        Get yfinance Ticker object with error handling
        """
        # Rate limiting
        self.rate_limiter.acquire()
        
        for attempt in range(self.config.max_retries):
            try:
                ticker = yf.Ticker(symbol)
                # Avoid relying on .info for validation (often slow / sometimes blocked).
                hist = ticker.history(period="5d", interval="1d")
                if hist is not None and not hist.empty:
                    return ticker
                raise ValueError(f"Invalid symbol or no price history available: {symbol}")
                    
            except Exception as e:
                logger.warning(f"Failed to get ticker for {symbol} (attempt {attempt + 1}/{self.config.max_retries}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise

    @staticmethod
    def _normalize_history(symbol: str, hist: pd.DataFrame, *, interval: str = "1d") -> pd.DataFrame:
        if hist is None or hist.empty:
            raise ValueError(f"No historical data available for {symbol}")

        df = hist.copy()

        # yfinance history typically uses DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Standardize columns
        col_map = {c.lower(): c for c in df.columns}
        def get_col(name: str) -> str:
            if name in df.columns:
                return name
            lower = name.lower()
            if lower in col_map:
                return col_map[lower]
            raise KeyError(name)

        # Adj Close can be missing depending on auto_adjust/back_adjust.
        adj_close = None
        try:
            adj_close = df[get_col("Adj Close")]
        except Exception:
            adj_close = None

        # Preserve timestamps for intraday pipelines.
        # - For daily data, callers primarily use the 'date' column.
        # - For intraday (e.g. 15m), callers should use the tz-aware 'ts' column.
        ts_index = df.index
        if ts_index.tz is None:
            ts_index = ts_index.tz_localize("UTC")

        out = pd.DataFrame(
            {
                "ts": ts_index,
                "date": df.index.date,
                "open": df[get_col("Open")].astype(float, errors="ignore"),
                "high": df[get_col("High")].astype(float, errors="ignore"),
                "low": df[get_col("Low")].astype(float, errors="ignore"),
                "close": df[get_col("Close")].astype(float, errors="ignore"),
                "volume": df[get_col("Volume")].fillna(0).astype(float, errors="ignore"),
                "adj_close": adj_close.astype(float, errors="ignore") if adj_close is not None else df[get_col("Close")].astype(float, errors="ignore"),
                "stock_symbol": symbol,
                "interval": interval,
            }
        )

        out = out.reset_index(drop=True)
        return out
    
    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        """
        Fetch historical price data
        
        Args:
            symbol: Stock symbol
            **kwargs: Additional parameters (period, interval, start, end, etc.)
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            ticker = self._get_ticker(symbol)
            
            # Get historical data
            days = kwargs.get("days")
            period = kwargs.get("period")
            interval = kwargs.get("interval", "1d")
            start = kwargs.get("start")
            end = kwargs.get("end")
            auto_adjust = kwargs.get("auto_adjust", False)

            if period is None and days is not None:
                # yfinance supports: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
                if days <= 5:
                    period = "5d"
                elif days <= 30:
                    period = "1mo"
                elif days <= 90:
                    period = "3mo"
                elif days <= 180:
                    period = "6mo"
                elif days <= 365:
                    period = "1y"
                elif days <= 730:
                    period = "2y"
                else:
                    period = "5y"

            for attempt in range(self.config.max_retries):
                try:
                    self.rate_limiter.acquire()
                    if start and end:
                        hist = ticker.history(start=start, end=end, interval=interval, auto_adjust=auto_adjust)
                    else:
                        hist = ticker.history(period=period or "1y", interval=interval, auto_adjust=auto_adjust)
                    df = self._normalize_history(symbol, hist, interval=interval)
                    logger.info(f"✅ Fetched {len(df)} price records for {symbol}")
                    return df
                except Exception as e:
                    logger.warning(
                        f"Failed to fetch price data for {symbol} (attempt {attempt + 1}/{self.config.max_retries}): {e}"
                    )
                    if attempt < self.config.max_retries - 1:
                        time.sleep(self.config.retry_delay * (2 ** attempt))
                        continue
                    raise
            
        except Exception as e:
            logger.error(f"Failed to fetch price data for {symbol}: {e}")
            raise
    
    def fetch_current_price(self, symbol: str) -> Optional[float]:
        """
        Fetch current price
        """
        try:
            ticker = self._get_ticker(symbol)
            
            # Get current price from info
            info = ticker.info
            current_price = info.get("regularMarketPrice") or info.get("currentPrice")
            
            if current_price is not None:
                return float(current_price)
            
            # Fallback to latest historical data
            hist = ticker.history(period="1d", interval="1m")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to fetch current price for {symbol}: {e}")
            return None
    
    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch symbol details and company information
        Uses optimized yfinance methods to reduce expensive API calls
        """
        try:
            ticker = self._get_ticker(symbol)
            
            # Use more efficient methods instead of relying solely on ticker.info
            # This follows yfinance best practices to reduce expensive quoteSummary calls
            
            # Get basic metadata (cheaper than full info)
            try:
                logger.debug(f"Getting history metadata for {symbol}")
                metadata = ticker.get_history_metadata()
                logger.debug(f"History metadata successful for {symbol}")
            except Exception as metadata_error:
                logger.warning(f"History metadata failed for {symbol}: {metadata_error}")
                metadata = {}
            
            # Get fast info as primary source (more reliable than full info)
            try:
                logger.debug(f"Getting fast info for {symbol}")
                fast_info = ticker.fast_info
                logger.debug(f"Fast info successful for {symbol}: {len(dict(fast_info))} fields")
            except Exception as fast_info_error:
                logger.warning(f"Fast info failed for {symbol}: {fast_info_error}")
                fast_info = {}
            
            # Get full info as fallback for missing critical fields
            info = {}
            try:
                logger.debug(f"Getting full info for {symbol} (fallback)")
                info = ticker.info
                logger.debug(f"Full info successful for {symbol}: {len(info) if info else 0} fields")
            except Exception as info_error:
                logger.warning(f"Full info failed for {symbol} (quoteSummary endpoint): {info_error}")
                # Create minimal info dict with basic symbol data
                info = {"symbol": symbol}
            
            # Combine data from multiple sources in order of preference
            details = {"symbol": symbol}
            
            # 1. Fast info (most reliable and efficient)
            if fast_info:
                details.update({
                    "name": fast_info.get("long_name") or fast_info.get("short_name", ""),
                    "sector": fast_info.get("sector", ""),
                    "industry": fast_info.get("industry", ""),
                    "market_cap": fast_info.get("market_cap"),
                    "pe_ratio": fast_info.get("trailing_pe") or fast_info.get("forward_pe"),
                    "pb_ratio": fast_info.get("price_to_book"),
                    "eps": fast_info.get("trailing_eps"),
                    "dividend_yield": fast_info.get("dividend_yield"),
                    "beta": fast_info.get("beta"),
                    "currency": fast_info.get("currency", "USD"),
                    "exchange": fast_info.get("exchange", ""),
                })
            
            # 2. Metadata for exchange/timezone info
            if metadata:
                details.update({
                    "exchange": details.get("exchange") or metadata.get("exchange", ""),
                    "currency": details.get("currency") or metadata.get("currency", "USD"),
                    "timezone": metadata.get("timezone", ""),
                })
            
            # 3. Full info for missing fields (fallback)
            missing_fields = [k for k, v in details.items() if v is None or v == ""]
            if missing_fields and info:
                field_mapping = {
                    "name": info.get("longName") or info.get("shortName"),
                    "sector": info.get("sector"),
                    "industry": info.get("industry"),
                    "market_cap": info.get("marketCap"),
                    "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                    "pb_ratio": info.get("priceToBook"),
                    "eps": info.get("trailingEps"),
                    "dividend_yield": info.get("dividendYield"),
                    "profit_margin": info.get("profitMargins"),
                    "current_ratio": info.get("currentRatio"),
                    "beta": info.get("beta"),
                    "description": info.get("longBusinessSummary"),
                    "country": info.get("country"),
                    "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                    "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                    "average_volume": info.get("averageVolume"),
                    "enterprise_value": info.get("enterpriseValue"),
                    "price_to_sales": info.get("priceToSalesTrailing12Months"),
                    "forward_pe": info.get("forwardPE"),
                    "peg_ratio": info.get("pegRatio"),
                }
                
                for field in missing_fields:
                    if field in field_mapping and field_mapping[field] is not None:
                        details[field] = field_mapping[field]
            
            # Get current price from history if not available
            if not details.get("market_cap") or not details.get("pe_ratio"):
                try:
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        current_price = float(hist["Close"].iloc[-1])
                        if not details.get("market_cap") and fast_info.get("shares"):
                            details["market_cap"] = current_price * fast_info.get("shares")
                        logger.debug(f"Used price history for missing data: {current_price}")
                except Exception as hist_error:
                    logger.warning(f"Price history fallback failed for {symbol}: {hist_error}")
            
            logger.info(f"✅ Fetched symbol details for {symbol}: {len([k for k, v in details.items() if v is not None])} non-null fields")
            return details
            
        except Exception as e:
            logger.error(f"Failed to fetch symbol details for {symbol}: {e}")
            raise
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamental financial data
        """
        logger.info(f"📊 Starting fundamentals fetch for {symbol}")
        
        try:
            # Step 1: Get symbol details (this is where the 404 happens)
            logger.debug(f"Step 1: Fetching symbol details for {symbol}")
            try:
                details = self.fetch_symbol_details(symbol)
                logger.debug(f"Step 1 SUCCESS: Got {len(details)} basic fields for {symbol}")
            except Exception as details_error:
                logger.error(f"Step 1 FAILED: Symbol details for {symbol}: {details_error}")
                raise
            
            # Step 2: Get ticker for financial statements
            logger.debug(f"Step 2: Getting ticker for financial statements for {symbol}")
            try:
                ticker = self._get_ticker(symbol)
                logger.debug(f"Step 2 SUCCESS: Ticker created for {symbol}")
            except Exception as ticker_error:
                logger.error(f"Step 2 FAILED: Ticker creation for {symbol}: {ticker_error}")
                raise
            
            # Step 3: Get financial statements
            logger.debug(f"Step 3: Fetching financial statements for {symbol}")
            
            financials = None
            balance_sheet = None
            cashflow = None
            
            try:
                financials = ticker.financials
                logger.debug(f"Step 3a - Financials: {financials.shape if not financials.empty else 'Empty'}")
            except Exception as fin_error:
                logger.warning(f"Step 3a FAILED: Financials for {symbol}: {fin_error}")
            
            try:
                balance_sheet = ticker.balance_sheet
                logger.debug(f"Step 3b - Balance Sheet: {balance_sheet.shape if not balance_sheet.empty else 'Empty'}")
            except Exception as bs_error:
                logger.warning(f"Step 3b FAILED: Balance sheet for {symbol}: {bs_error}")
            
            try:
                cashflow = ticker.cashflow
                logger.debug(f"Step 3c - Cashflow: {cashflow.shape if not cashflow.empty else 'Empty'}")
            except Exception as cf_error:
                logger.warning(f"Step 3c FAILED: Cashflow for {symbol}: {cf_error}")
            
            # Step 4: Add financial data to details
            logger.debug(f"Step 4: Processing financial data for {symbol}")
            
            # Add recent financial data
            if financials is not None and not financials.empty:
                latest_financials = financials.iloc[:, 0]  # Most recent period
                details.update({
                    "revenue": latest_financials.get("Total Revenue"),
                    "gross_profit": latest_financials.get("Gross Profit"),
                    "operating_income": latest_financials.get("Operating Income"),
                    "net_income": latest_financials.get("Net Income"),
                    "total_assets": latest_financials.get("Total Assets"),
                    "total_liabilities": latest_financials.get("Total Liab"),
                })
                logger.debug(f"Step 4a: Added income statement data for {symbol}")
            
            if balance_sheet is not None and not balance_sheet.empty:
                latest_balance = balance_sheet.iloc[:, 0]
                details.update({
                    "cash_and_equivalents": latest_balance.get("Cash And Cash Equivalents"),
                    "short_term_investments": latest_balance.get("Short Term Investments"),
                    "current_assets": latest_balance.get("Total Current Assets") or latest_balance.get("Current Assets"),
                    "current_liabilities": latest_balance.get("Total Current Liabilities") or latest_balance.get("Current Liabilities"),
                    "long_term_debt": latest_balance.get("Long Term Debt"),
                    "short_term_debt": latest_balance.get("Current Debt"),  # Updated: Current Debt is the correct field
                    "total_debt": latest_balance.get("Total Debt"),  # Added: Total Debt from Yahoo
                    "total_equity": latest_balance.get("Stockholders Equity"),  # Moved from financials to balance sheet
                    "property_plant_equipment": latest_balance.get("Net PPE"),
                })
                logger.debug(f"Step 4b: Added balance sheet data for {symbol}")
            
            if cashflow is not None and not cashflow.empty:
                latest_cashflow = cashflow.iloc[:, 0]
                details.update({
                    "operating_cash_flow": latest_cashflow.get("Operating Cash Flow"),
                    "investing_cash_flow": latest_cashflow.get("Investing Cash Flow"),
                    "financing_cash_flow": latest_cashflow.get("Financing Cash Flow"),
                    "free_cash_flow": latest_cashflow.get("Operating Cash Flow") - latest_cashflow.get("Capital Expenditure"),
                })
                logger.debug(f"Step 4c: Added cash flow data for {symbol}")
            
            # Step 5: Calculate derived metrics and extract additional fields from info
            logger.debug(f"Step 5: Calculating derived metrics for {symbol}")

            try:
                info = ticker.info
            except Exception:
                info = {}

            try:
                fast_info = ticker.fast_info
            except Exception:
                fast_info = {}
            
            # Extract all key fundamentals from ticker.info (primary source for ratios/metrics)
            if info:
                yahoo_field_mapping = {
                    # Valuation ratios
                    "price_to_sales": info.get("priceToSalesTrailing12Months"),
                    "price_to_book": info.get("priceToBook"),
                    "enterprise_to_revenue": info.get("enterpriseToRevenue"),
                    "enterprise_to_ebitda": info.get("enterpriseToEbitda"),
                    "peg_ratio": info.get("pegRatio"),
                    "forward_pe": info.get("forwardPE"),
                    # Profitability
                    "profit_margin": info.get("profitMargins"),
                    "gross_margin": info.get("grossMargins"),
                    "operating_margin": info.get("operatingMargins"),
                    "ebitda_margin": info.get("ebitdaMargins"),
                    # Returns
                    "roe": info.get("returnOnEquity"),
                    "roa": info.get("returnOnAssets"),
                    # Growth
                    "revenue_growth": info.get("revenueGrowth"),
                    "earnings_growth": info.get("earningsGrowth"),
                    # Financial health
                    "current_ratio": info.get("currentRatio"),
                    "quick_ratio": info.get("quickRatio"),
                    "debt_to_equity": info.get("debtToEquity"),
                    # Dividends
                    "dividend_yield": info.get("dividendYield"),
                    "dividend_rate": info.get("dividendRate"),
                    "payout_ratio": info.get("payoutRatio"),
                    # Cash flow
                    "free_cash_flow_yahoo": info.get("freeCashflow"),
                    "operating_cash_flow_yahoo": info.get("operatingCashflow"),
                    # Additional metrics
                    "total_cash": info.get("totalCash"),
                    "total_debt_yahoo": info.get("totalDebt"),
                    "ebitda": info.get("ebitda"),
                    "total_revenue": info.get("totalRevenue"),
                    "gross_profits": info.get("grossProfits"),
                    "book_value": info.get("bookValue"),
                    "revenue_per_share": info.get("revenuePerShare"),
                    "eps_forward": info.get("epsForward"),
                    "eps_trailing": info.get("trailingEps"),
                }
                
                # Only add fields that have values and aren't already set
                for field, value in yahoo_field_mapping.items():
                    if value is not None and details.get(field) is None:
                        details[field] = value
                
                logger.debug(f"Step 5a: Extracted {sum(1 for v in yahoo_field_mapping.values() if v is not None)} fields from ticker.info")
            
            # Always calculate debt/equity ratio from balance sheet components for accuracy
            total_equity = details.get("total_equity")
            
            # Prefer Yahoo's total debt if available, otherwise calculate from components
            total_debt = details.get("total_debt")
            if total_debt is None:
                total_debt = 0
                # Sum all debt components
                if details.get("long_term_debt"):
                    total_debt += details.get("long_term_debt")
                if details.get("short_term_debt"):
                    total_debt += details.get("short_term_debt")
            
            # Calculate ratio if we have both components
            if total_debt is not None and total_equity is not None and total_equity != 0:
                details["debt_to_equity"] = total_debt / total_equity
                logger.info(f"Calculated debt/equity ratio for {symbol}: {details['debt_to_equity']:.3f}")
            else:
                logger.warning(f"Could not calculate debt/equity ratio for {symbol}: missing debt or equity data")

            if details.get("profit_margin") is None:
                try:
                    revenue = details.get("revenue")
                    net_income = details.get("net_income")
                    if revenue is not None and net_income is not None and float(revenue) != 0:
                        details["profit_margin"] = float(net_income) / float(revenue)
                except Exception:
                    pass

            if details.get("current_ratio") is None:
                try:
                    ca = details.get("current_assets")
                    cl = details.get("current_liabilities")
                    if ca is not None and cl is not None and float(cl) != 0:
                        details["current_ratio"] = float(ca) / float(cl)
                except Exception:
                    pass

            if details.get("dividend_yield") is None:
                try:
                    dy = info.get("dividendYield")
                    if dy is not None:
                        details["dividend_yield"] = dy
                    else:
                        annual_div = info.get("trailingAnnualDividendRate") or info.get("dividendRate")
                        price = (
                            info.get("regularMarketPrice")
                            or info.get("currentPrice")
                            or (fast_info.get("last_price") if isinstance(fast_info, dict) else None)
                        )
                        if annual_div is not None and price is not None and float(price) != 0:
                            details["dividend_yield"] = float(annual_div) / float(price)
                except Exception:
                    pass

            if details.get("forward_pe") is None:
                try:
                    fpe = info.get("forwardPE")
                    if fpe is not None:
                        details["forward_pe"] = fpe
                    else:
                        eps_fwd = info.get("epsForward")
                        price = (
                            info.get("regularMarketPrice")
                            or info.get("currentPrice")
                            or (fast_info.get("last_price") if isinstance(fast_info, dict) else None)
                        )
                        if eps_fwd is not None and price is not None and float(eps_fwd) != 0:
                            details["forward_pe"] = float(price) / float(eps_fwd)
                except Exception:
                    pass
            
            logger.info(f"✅ Fetched fundamentals for {symbol}")
            return details
            
        except Exception as e:
            logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
            # Return basic details if financial statements fail
            return self.fetch_symbol_details(symbol)
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch recent news articles
        Note: News may be limited outside market hours (holidays, weekends, after-hours)
        """
        try:
            ticker = self._get_ticker(symbol)
            news = ticker.news
            
            if not news:
                logger.info(f"No news returned for {symbol} (market may be closed)")
                return []
            
            articles = []
            for article in news[:limit]:
                # Yahoo now returns only 'id' and 'content'; extract what we can
                content = article.get("content", {})
                # Try to extract title/publisher from content or use defaults
                title = content.get("title") or content.get("headline") or "No title"
                publisher = content.get("publisher") or content.get("source") or "Unknown"
                link = content.get("url") or content.get("link") or ""
                pub_time = content.get("publishTime") or article.get("providerPublishTime")
                summary = content.get("summary") or content.get("description") or "No summary"
                
                # If no meaningful content, likely market closed
                if title == "No title" and not link:
                    logger.info(f"Limited news content for {symbol} (market may be closed)")
                
                articles.append({
                    "symbol": symbol,
                    "title": title,
                    "link": link,
                    "publisher": publisher,
                    "published": pub_time,
                    "summary": summary,
                    "raw_keys": list(article.keys()),
                    "content_keys": list(content.keys()) if isinstance(content, dict) else []
                })
            logger.info(f"✅ Fetched {len(articles)} news articles for {symbol}")
            return articles
            
        except Exception as e:
            logger.error(f"Failed to fetch news for {symbol}: {e}")
            return []
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Fetch earnings data using the correct calendar API
        """
        try:
            ticker = self._get_ticker(symbol)
            
            # Get earnings calendar data (correct API)
            calendar = ticker.calendar
            
            earnings_data = []
            
            if calendar and isinstance(calendar, dict):
                earnings_dates = calendar.get("Earnings Date", [])
                eps_high = calendar.get("Earnings High")
                eps_low = calendar.get("Earnings Low") 
                eps_avg = calendar.get("Earnings Average")
                revenue_high = calendar.get("Revenue High")
                revenue_low = calendar.get("Revenue Low")
                revenue_avg = calendar.get("Revenue Average")
                
                # Process each earnings date
                for i, earnings_date in enumerate(earnings_dates):
                    earnings_at = None
                    try:
                        if isinstance(earnings_date, pd.Timestamp):
                            earnings_at = earnings_date.to_pydatetime().isoformat()
                        elif isinstance(earnings_date, datetime):
                            earnings_at = earnings_date.isoformat()
                    except Exception:
                        earnings_at = None

                    earnings_data.append({
                        "symbol": symbol,
                        "earnings_date": earnings_date.strftime("%Y-%m-%d") if hasattr(earnings_date, 'strftime') else str(earnings_date),
                        "earnings_at": earnings_at,
                        "earnings_timezone": "America/New_York",
                        "eps_estimate": eps_avg,
                        "eps_high": eps_high,
                        "eps_low": eps_low,
                        "revenue_estimate": revenue_avg,
                        "revenue_high": revenue_high,
                        "revenue_low": revenue_low,
                        "quarter": self._get_current_quarter(),
                        "year": earnings_date.year if hasattr(earnings_date, 'year') else datetime.now().year
                    })
            
            logger.info(f"✅ Fetched {len(earnings_data)} earnings records for {symbol}")
            return earnings_data
            
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {symbol}: {e}")
            return []
    
    def _get_current_quarter(self) -> int:
        """Get current quarter (1-4)"""
        from datetime import datetime
        month = datetime.now().month
        return (month - 1) // 3 + 1
    
    def fetch_technical_indicators(self, symbol: str, indicator_type: str = "SMA", **kwargs) -> Dict[str, Any]:
        """
        Fetch technical indicators (calculated from historical data)
        """
        try:
            # Get historical data for calculations
            period = kwargs.get("period", "1y")
            ticker = self._get_ticker(symbol)
            hist = ticker.history(period=period)
            
            if hist.empty:
                raise ValueError(f"No historical data available for {symbol}")
            
            result = {
                "symbol": symbol,
                "indicator_type": indicator_type,
                "calculated_at": datetime.now().isoformat()
            }
            
            # Calculate indicators based on type
            if indicator_type.upper() == "SMA":
                window = kwargs.get("time_period", 20)
                sma = hist["Close"].rolling(window=window).mean()
                result[f"sma_{window}"] = sma.iloc[-1]
                
            elif indicator_type.upper() == "EMA":
                window = kwargs.get("time_period", 20)
                ema = hist["Close"].ewm(span=window).mean()
                result[f"ema_{window}"] = ema.iloc[-1]
                
            elif indicator_type.upper() == "RSI":
                window = kwargs.get("time_period", 14)
                delta = hist["Close"].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                result[f"rsi_{window}"] = rsi.iloc[-1]
                
            elif indicator_type.upper() == "MACD":
                fast = kwargs.get("fastperiod", 12)
                slow = kwargs.get("slowperiod", 26)
                signal = kwargs.get("signalperiod", 9)
                
                ema_fast = hist["Close"].ewm(span=fast).mean()
                ema_slow = hist["Close"].ewm(span=slow).mean()
                macd_line = ema_fast - ema_slow
                signal_line = macd_line.ewm(span=signal).mean()
                histogram = macd_line - signal_line
                
                result.update({
                    "macd": macd_line.iloc[-1],
                    "macd_signal": signal_line.iloc[-1],
                    "macd_histogram": histogram.iloc[-1]
                })
                
            elif indicator_type.upper() == "BB":
                window = kwargs.get("time_period", 20)
                std_dev = kwargs.get("nbdevup", 2)
                
                sma = hist["Close"].rolling(window=window).mean()
                std = hist["Close"].rolling(window=window).std()
                
                upper_band = sma + (std * std_dev)
                lower_band = sma - (std * std_dev)
                
                result.update({
                    "bb_upper": upper_band.iloc[-1],
                    "bb_middle": sma.iloc[-1],
                    "bb_lower": lower_band.iloc[-1],
                    "bb_width": (upper_band.iloc[-1] - lower_band.iloc[-1]) / sma.iloc[-1]
                })
                
            elif indicator_type.upper() == "ATR":
                window = kwargs.get("time_period", 14)
                
                high_low = hist["High"] - hist["Low"]
                high_close = abs(hist["High"] - hist["Close"].shift())
                low_close = abs(hist["Low"] - hist["Close"].shift())
                
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(window=window).mean()
                
                result[f"atr_{window}"] = atr.iloc[-1]
            
            logger.info(f"✅ Calculated {indicator_type} for {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to calculate technical indicators for {symbol}: {e}")
            raise
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch industry peers using niche identification from business summary and industryKey.
        """
        try:
            ticker = self._get_ticker(symbol)
            info = ticker.info
            
            sector = info.get("sector", "")
            industry = info.get("industry", "")
            industry_key = info.get("industryKey", "")
            summary = info.get("longBusinessSummary", "").lower()
            
            # Niche identification keywords (ordered by specificity)
            niche_keywords = {
                "bitcoin_mining": ["bitcoin mining", "bitcoin", "crypto mining", "blockchain mining", "digital asset mining"],
                "cloud_gpu_ai": ["gpu compute", "genai", "ai infrastructure", "cloud platform", "gpu cloud", "ai compute"],
                "data_center": ["data center", "data centre", "datacenter", "colocation"],
                "cloud_infrastructure": ["cloud infrastructure", "cloud computing", "iaas", "paas", "saas infrastructure"],
                "semiconductor_equipment": ["semiconductor equipment", "chip equipment", "wafer fabrication"],
                "renewable_energy": ["renewable energy", "solar", "wind", "clean energy"],
                "electric_vehicle": ["electric vehicle", "ev", "battery", "charging"],
                "fintech_payments": ["fintech", "payments", "digital payments", "financial technology"],
                "biotech": ["biotechnology", "biotech", "pharmaceutical", "drug discovery"],
                "cybersecurity": ["cybersecurity", "network security", "information security"],
                "e-commerce": ["e-commerce", "online marketplace", "online retail"]
            }
            
            # Detect niche from summary
            detected_niche = None
            for niche, keywords in niche_keywords.items():
                if any(kw in summary for kw in keywords):
                    detected_niche = niche
                    break
            
            # Niche-specific peer lists (more direct competitors)
            niche_peers = {
                "cloud_gpu_ai": ["NVDA", "AMD", "GOOGL", "MSFT", "AMZN", "AAPL", "META", "TSLA", "INTC", "IBM"],
                "data_center": ["EQIX", "DLR", "PLD", "AMT", "CCI", "EXR", "COR", "CONE", "QTS", "LAMR"],
                "bitcoin_mining": ["RIOT", "MARA", "CLSK", "HUT", "BITF", "CIFR", "HIVE", "ARBK", "BTBT", "SDIG"],
                "cloud_infrastructure": ["AMZN", "MSFT", "GOOGL", "AAPL", "META", "TSLA", "NVDA", "INTC", "AMD", "IBM"],
                "semiconductor_equipment": ["ASML", "LRCX", "KLAC", "AMAT", "TER", "MKSI", "ICHR", "COHR", "VECO", "NANO"],
                "renewable_energy": ["NEE", "ENPH", "SEDG", "FSLR", "SUNW", "RUN", "CSIQ", "JKS", "DQ", "PEG"],
                "electric_vehicle": ["TSLA", "RIVN", "LCID", "NIO", "XPEV", "LI", "GM", "F", "HYLN", "FSR"],
                "fintech_payments": ["PYPL", "SQ", "MA", "V", "AFRM", "UPST", "BLKB", "INTU", "ADP", "FIS"],
                "biotech": ["JNJ", "PFE", "UNH", "ABBV", "MRK", "TMO", "ABT", "AMGN", "GILD", "BMY"],
                "cybersecurity": ["PANW", "CRWD", "ZS", "FTNT", "OKTA", "S", "MNDT", "CHKP", "QUAL", "CYBR"],
                "e-commerce": ["AMZN", "SHOP", "EBAY", "MELI", "BABA", "ETSY", "RVLV", "W", "BIGC", "SE"]
            }
            
            # Fallback industry-specific lists
            industry_peers = {
                "capital-markets": ["JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK", "SPGI", "ICE"],
                "software-infrastructure": ["MSFT", "ORCL", "SAP", "INTU", "ADBE", "CRM", "NOW", "TEAM", "WDAY", "ZS"],
                "semiconductors": ["NVDA", "AMD", "INTC", "MU", "QCOM", "TXN", "AVGO", "MRVL", "LRCX", "KLAC"],
                "telecom-services": ["T", "VZ", "TMUS", "S", "CMCSA", "CHTR", "VOD", "TU", "AMX", "TEF"],
                "banks-diversified": ["JPM", "BAC", "WFC", "C", "GS", "MS", "USB", "PNC", "COF", "TFC"],
                "insurance-diversified": ["BRK-A", "BRK-B", "AIG", "MET", "PRU", "ALL", "HIG", "TRV", "CINF", "AFL"],
                "reits": ["AMT", "PLD", "CCI", "EQIX", "PSA", "SPG", "DLR", "EXR", "PRO", "O"]
            }
            
            peers = []
            niche_used = None
            
            # Try niche-specific peers first
            if detected_niche and detected_niche in niche_peers:
                peer_symbols = [s for s in niche_peers[detected_niche] if s != symbol]
                peers = peer_symbols[:10]
                niche_used = detected_niche
            
            # Fallback to industryKey mapping
            if not peers and industry_key in industry_peers:
                peer_symbols = [s for s in industry_peers[industry_key] if s != symbol]
                peers = peer_symbols[:10]
                niche_used = f"industry: {industry_key}"
            
            # Final fallback to sector generic list
            if not peers:
                sector_generic = {
                    "Technology": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "ADBE", "CRM", "NFLX"],
                    "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK", "SPGI", "ICE"],
                    "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "TMO", "ABT", "MRK", "MDT", "AMGN", "GILD"]
                }
                if sector in sector_generic:
                    peers = [s for s in sector_generic[sector] if s != symbol][:10]
                    niche_used = f"sector: {sector}"
            
            note = f"Peers derived from {niche_used} ({len(peers)} peers)" if niche_used else f"No specific niche found for {industry_key}"
            
            return {
                "symbol": symbol,
                "sector": sector,
                "industry": industry,
                "industry_key": industry_key,
                "detected_niche": detected_niche,
                "peers": peers,
                "note": note
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch industry peers for {symbol}: {e}")
            return {"symbol": symbol, "peers": [], "error": str(e)}

    def fetch_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch corporate actions (dividends/splits) from Yahoo via yfinance."""
        try:
            ticker = self._get_ticker(symbol)
            self.rate_limiter.acquire()
            actions = ticker.actions
            if actions is None or actions.empty:
                return []

            out: List[Dict[str, Any]] = []
            tmp = actions.copy().reset_index()
            # yfinance uses DatetimeIndex; normalize to date
            date_col = "Date" if "Date" in tmp.columns else tmp.columns[0]
            for _, row in tmp.iterrows():
                dt = row.get(date_col)
                d = pd.to_datetime(dt, errors="coerce")
                d_str = d.date().isoformat() if not pd.isna(d) else None
                # Prefer returning explicit entries for each action field
                if "Dividends" in tmp.columns and row.get("Dividends") not in (None, 0, 0.0):
                    out.append({"symbol": symbol, "date": d_str, "action_type": "dividend", "value": float(row.get("Dividends"))})
                if "Stock Splits" in tmp.columns and row.get("Stock Splits") not in (None, 0, 0.0):
                    out.append({"symbol": symbol, "date": d_str, "action_type": "split", "value": float(row.get("Stock Splits"))})
            return out
        except Exception as e:
            logger.warning(f"Failed to fetch actions for {symbol}: {e}")
            return []

    def fetch_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch dividend time series from Yahoo via yfinance."""
        try:
            ticker = self._get_ticker(symbol)
            self.rate_limiter.acquire()
            div = ticker.dividends
            if div is None or div.empty:
                return []
            out: List[Dict[str, Any]] = []
            for idx, val in div.items():
                d = pd.to_datetime(idx, errors="coerce")
                if pd.isna(d):
                    continue
                if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                    continue
                out.append({"symbol": symbol, "date": d.date().isoformat(), "dividend": float(val)})
            return out
        except Exception as e:
            logger.warning(f"Failed to fetch dividends for {symbol}: {e}")
            return []

    def fetch_splits(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch stock split time series from Yahoo via yfinance."""
        try:
            ticker = self._get_ticker(symbol)
            self.rate_limiter.acquire()
            splits = ticker.splits
            if splits is None or splits.empty:
                return []
            out: List[Dict[str, Any]] = []
            for idx, val in splits.items():
                d = pd.to_datetime(idx, errors="coerce")
                if pd.isna(d):
                    continue
                if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                    continue
                out.append({"symbol": symbol, "date": d.date().isoformat(), "split_ratio": float(val)})
            return out
        except Exception as e:
            logger.warning(f"Failed to fetch splits for {symbol}: {e}")
            return []

    @staticmethod
    def _normalize_statement_df(df: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
        """Normalize yfinance statement DataFrame into a list of period records."""
        if df is None or getattr(df, "empty", True):
            return []

        tmp = df.copy()
        # yfinance statements typically have line-items as index, periods as columns
        tmp = tmp.fillna(value=pd.NA)

        records: List[Dict[str, Any]] = []
        for col in tmp.columns:
            period = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            series = tmp[col]
            payload: Dict[str, Any] = {"period": period}
            for k, v in series.items():
                key = str(k).strip()
                if v is pd.NA or v is None:
                    payload[key] = None
                    continue
                try:
                    payload[key] = float(v) if pd.notna(v) else None
                except Exception:
                    payload[key] = str(v)
            records.append(payload)

        return records

    def fetch_financial_statements(self, symbol: str, *, quarterly: bool = True) -> Dict[str, Any]:
        """Fetch income statement, balance sheet, and cash flow statements."""
        try:
            ticker = self._get_ticker(symbol)
            self.rate_limiter.acquire()

            if quarterly:
                income = getattr(ticker, "quarterly_financials", None)
                balance = getattr(ticker, "quarterly_balance_sheet", None)
                cash = getattr(ticker, "quarterly_cashflow", None)
            else:
                income = getattr(ticker, "financials", None)
                balance = getattr(ticker, "balance_sheet", None)
                cash = getattr(ticker, "cashflow", None)

            return {
                "symbol": symbol,
                "periodicity": "quarterly" if quarterly else "annual",
                "income_statement": self._normalize_statement_df(income),
                "balance_sheet": self._normalize_statement_df(balance),
                "cash_flow": self._normalize_statement_df(cash),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch financial statements for {symbol}: {e}")
            return {
                "symbol": symbol,
                "periodicity": "quarterly" if quarterly else "annual",
                "income_statement": [],
                "balance_sheet": [],
                "cash_flow": [],
                "error": str(e),
            }

    def fetch_daily_indicator_bundle(self, symbol: str, *, period: str = "1y") -> Dict[str, Any]:
        """Compute a standard daily indicator bundle from historical prices.

        This is a convenience method for refresh pipelines that want a single call to
        compute commonly used indicators; it does not replace richer indicator services.
        """
        ticker = self._get_ticker(symbol)
        self.rate_limiter.acquire()
        hist = ticker.history(period=period, interval="1d")
        if hist is None or hist.empty:
            raise ValueError(f"No historical data available for {symbol}")

        close = hist["Close"].astype(float)
        high = hist["High"].astype(float)
        low = hist["Low"].astype(float)

        sma_20 = close.rolling(window=20).mean().iloc[-1]
        sma_50 = close.rolling(window=50).mean().iloc[-1]
        sma_200 = close.rolling(window=200).mean().iloc[-1]
        ema_20 = close.ewm(span=20).mean().iloc[-1]

        # RSI(14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi_14 = (100 - (100 / (1 + rs))).iloc[-1]

        # MACD(12,26,9)
        ema_12 = close.ewm(span=12).mean()
        ema_26 = close.ewm(span=26).mean()
        macd_line = ema_12 - ema_26
        macd_signal = macd_line.ewm(span=9).mean()
        macd_hist = (macd_line - macd_signal).iloc[-1]

        # ATR(14)
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr_14 = tr.rolling(window=14).mean().iloc[-1]

        last_ts = hist.index[-1]
        as_of_date = pd.to_datetime(last_ts, errors="coerce").date().isoformat() if last_ts is not None else None

        return {
            "stock_symbol": symbol,
            "trade_date": as_of_date,
            "sma_20": self._to_jsonable(sma_20),
            "sma_50": self._to_jsonable(sma_50),
            "sma_200": self._to_jsonable(sma_200),
            "ema_20": self._to_jsonable(ema_20),
            "rsi_14": self._to_jsonable(rsi_14),
            "macd": self._to_jsonable(macd_line.iloc[-1]),
            "macd_signal": self._to_jsonable(macd_signal.iloc[-1]),
            "macd_hist": self._to_jsonable(macd_hist),
            "atr_14": self._to_jsonable(atr_14),
            "source": "yahoo_finance",
        }

    @staticmethod
    def _normalize_earnings_calendar_df(df: Optional[pd.DataFrame], *, default_date: Optional[str] = None) -> List[Dict[str, Any]]:
        if df is None or getattr(df, "empty", True):
            return []

        tmp = df.copy()
        tmp.columns = [
            str(c)
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("-", "_")
            for c in tmp.columns
        ]

        def _pick_col(candidates: List[str]) -> Optional[str]:
            for c in candidates:
                if c in tmp.columns:
                    return c
            return None

        symbol_col = _pick_col(["symbol", "ticker"])
        company_col = _pick_col(["company", "company_name", "name"])
        date_col = _pick_col(["earnings_date", "date", "report_date", "earningsdate"])
        time_col = _pick_col(["call_time", "time", "timing"])
        eps_est_col = _pick_col(["eps_estimate", "eps_est", "eps_estimated"])
        eps_act_col = _pick_col(["reported_eps", "eps_actual", "eps"])

        if symbol_col is None:
            return []

        tmp["symbol"] = tmp[symbol_col].astype(str)
        if company_col is not None:
            tmp["company_name"] = tmp[company_col].astype(str)

        if date_col is not None:
            parsed = pd.to_datetime(tmp[date_col], errors="coerce")
            tmp["earnings_date"] = parsed.dt.date
        elif default_date:
            tmp["earnings_date"] = pd.to_datetime(default_date, errors="coerce").date()
        else:
            return []

        if time_col is not None:
            tmp["time"] = tmp[time_col]

        if eps_est_col is not None:
            tmp["eps_estimate"] = pd.to_numeric(tmp[eps_est_col], errors="coerce")
        if eps_act_col is not None:
            tmp["eps_actual"] = pd.to_numeric(tmp[eps_act_col], errors="coerce")

        out_cols = [
            "symbol",
            "company_name",
            "earnings_date",
            "eps_estimate",
            "eps_actual",
            "time",
        ]
        for c in out_cols:
            if c not in tmp.columns:
                tmp[c] = None

        tmp = tmp[out_cols]
        tmp = tmp[tmp["earnings_date"].notna()]
        return tmp.to_dict(orient="records")

    def fetch_earnings_for_date(self, earnings_date: str, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        try:
            from yahoo_fin import stock_info as si
        except Exception as e:
            logger.warning(f"yahoo_fin not available for earnings-for-date ({earnings_date}): {e}")
            return []

        try:
            self.rate_limiter.acquire()
            df = si.get_earnings_for_date(earnings_date)
            rows = self._normalize_earnings_calendar_df(df, default_date=earnings_date)
            if symbols:
                sset = {s.upper() for s in symbols}
                rows = [r for r in rows if str(r.get("symbol", "")).upper() in sset]
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch earnings for date {earnings_date}: {e}")
            return []

    def _fetch_earnings_calendar_fallback(self, symbols: List[str], start_date: str, end_date: str) -> List[Dict[str, Any]]:
        try:
            earnings_data: List[Dict[str, Any]] = []
            for symbol in symbols:
                try:
                    earnings_history = self.fetch_earnings(symbol)
                    symbol_info = self.fetch_symbol_details(symbol)

                    for earnings in earnings_history:
                        earnings_date = earnings.get("earnings_date")
                        if not earnings_date:
                            continue

                        try:
                            if isinstance(earnings_date, str):
                                earnings_dt = datetime.strptime(earnings_date, "%Y-%m-%d")
                            else:
                                earnings_dt = datetime.fromtimestamp(earnings_date)

                            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

                            if start_dt <= earnings_dt <= end_dt:
                                earnings_data.append({
                                    "symbol": symbol,
                                    "company_name": symbol_info.get("shortName", symbol),
                                    "earnings_date": earnings_dt.date().isoformat(),
                                    "eps_estimate": earnings.get("eps_estimate"),
                                    "eps_actual": earnings.get("eps_actual"),
                                    "revenue_estimate": earnings.get("revenue_estimate"),
                                    "revenue_actual": earnings.get("revenue_actual"),
                                    "quarter": earnings.get("quarter"),
                                    "year": earnings.get("year"),
                                    "time": "After Market Close" if getattr(earnings_dt, "hour", 0) >= 16 else "Before Market Open",
                                    "market_cap": symbol_info.get("marketCap"),
                                    "sector": symbol_info.get("sector"),
                                    "industry": symbol_info.get("industry"),
                                })
                        except (ValueError, TypeError):
                            continue
                except Exception as e:
                    logger.warning(f"Failed to fetch earnings for {symbol}: {e}")
                    continue

            earnings_data.sort(key=lambda x: (x.get("earnings_date"), x.get("symbol")))
            logger.info(f"✅ Fetched {len(earnings_data)} earnings calendar entries (fallback)")
            return earnings_data
        except Exception as e:
            logger.error(f"Failed to fetch earnings calendar (fallback): {e}")
            return []
    
    def fetch_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """
        Fetch earnings calendar data for multiple symbols and date range.
        Args:
            symbols: List of symbols (if None, fetches major indices)
            start_date: Start date in YYYY-MM-DD format (if None, uses today)
            end_date: End date in YYYY-MM-DD format (if None, uses start_date + 90 days)
        """
        # If symbols are not provided, default to major symbols (kept for fallback behavior).
        if not symbols:
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "JNJ", "V"]

        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        if not end_date:
            end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

        # Preferred path: yahoo_fin earnings calendar scrape.
        try:
            from yahoo_fin import stock_info as si
            self.rate_limiter.acquire()
            df = si.get_earnings_calendar()
            rows = self._normalize_earnings_calendar_df(df)
            if not rows:
                raise ValueError("Empty earnings calendar from yahoo_fin")

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            sset = {s.upper() for s in symbols} if symbols else None

            filtered: List[Dict[str, Any]] = []
            for r in rows:
                d = r.get("earnings_date")
                if not d:
                    continue
                if isinstance(d, str):
                    d_val = pd.to_datetime(d, errors="coerce").date() if d else None
                else:
                    d_val = d
                if d_val is None:
                    continue
                if not (start_dt <= d_val <= end_dt):
                    continue
                sym = str(r.get("symbol", "")).upper()
                if sset is not None and sym not in sset:
                    continue
                r["earnings_date"] = d_val.isoformat()
                filtered.append(r)

            filtered.sort(key=lambda x: (x.get("earnings_date"), x.get("symbol")))
            logger.info(f"✅ Fetched {len(filtered)} earnings calendar entries (yahoo_fin)")
            return filtered
        except Exception as e:
            logger.warning(f"yahoo_fin earnings calendar failed, falling back to yfinance-based approach: {e}")

        return self._fetch_earnings_calendar_fallback(symbols, start_date, end_date)
    
    def is_available(self) -> bool:
        """
        Check if Yahoo Finance service is available
        """
        try:
            # Test with a common symbol
            ticker = yf.Ticker("AAPL")
            info = ticker.info
            return info is not None and 'regularMarketPrice' in info
        except Exception as e:
            logger.error(f"Yahoo Finance service unavailable: {e}")
            return False

    def fetch_quarterly_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch quarterly earnings history from Yahoo income_stmt and cash_flow."""
        ticker = yf.Ticker(symbol)
        try:
            income_stmt = ticker.income_stmt
            cash_flow = ticker.cash_flow

            if income_stmt is None or income_stmt.empty:
                logger.warning(f"No income statement found for {symbol}")
                return []

            # Normalize to list of quarters with key metrics
            earnings_history = []
            for i, col in enumerate(income_stmt.columns):
                period = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
                record = {
                    "period": period,
                    "revenue": self._safe_get(income_stmt, "Total Revenue", i),
                    "gross_profit": self._safe_get(income_stmt, "Gross Profit", i),
                    "operating_income": self._safe_get(income_stmt, "Operating Income", i),
                    "net_income": self._safe_get(income_stmt, "Net Income", i),
                    "eps_basic": self._safe_get(income_stmt, "Basic EPS", i),
                    "eps_diluted": self._safe_get(income_stmt, "Diluted EPS", i),
                }
                # Add cash flow metrics if available
                if cash_flow is not None and not cash_flow.empty and i < len(cash_flow.columns):
                    record["operating_cash_flow"] = self._safe_get(cash_flow, "Operating Cash Flow", i)
                    record["free_cash_flow"] = self._safe_get(cash_flow, "Free Cash Flow", i)
                earnings_history.append(record)
            return earnings_history
        except Exception as e:
            logger.error(f"Failed to fetch quarterly earnings for {symbol}: {e}")
            return []

    def _safe_get(self, df, key, idx):
        """Helper to safely get a value from DataFrame by index."""
        try:
            if key in df.index and idx < len(df.columns):
                val = df.loc[key].iloc[idx]
                return float(val) if pd.notna(val) else None
        except Exception:
            pass
        return None

    def fetch_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch analyst recommendations via Finnhub fallback if Yahoo not available."""
        # First try Yahoo (if they provide it in the future)
        # For now, use Finnhub as fallback
        return self._fetch_finnhub_analyst_recommendations(symbol)

    def _fetch_finnhub_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch analyst recommendations from Finnhub."""
        import os
        import requests

        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key:
            logger.info("FINNHUB_API_KEY not set; analyst recommendations unavailable")
            return []  # No mock data

        url = "https://finnhub.io/api/v1/stock/recommendation"
        params = {"symbol": symbol, "token": api_key}
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                return []
            # Normalize fields
            recommendations = []
            for rec in data:
                recommendations.append({
                    "period": rec.get("period"),
                    "strong_buy": rec.get("strongBuy"),
                    "buy": rec.get("buy"),
                    "hold": rec.get("hold"),
                    "sell": rec.get("sell"),
                    "strong_sell": rec.get("strongSell"),
                    "source": "finnhub"
                })
            return recommendations
        except Exception as e:
            logger.error(f"Failed to fetch Finnhub analyst recommendations for {symbol}: {e}")
            return []
