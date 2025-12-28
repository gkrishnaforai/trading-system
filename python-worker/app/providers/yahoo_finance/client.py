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

        logging.getLogger("yfinance").setLevel(logging.WARNING)
        logging.getLogger("yfinance.scrapers").setLevel(logging.WARNING)
        logging.getLogger("yfinance.scrapers.fundamentals").setLevel(logging.WARNING)
        
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
        """
        try:
            ticker = self._get_ticker(symbol)
            info = ticker.info
            
            if not info:
                raise ValueError(f"No symbol details available for {symbol}")
            
            # Normalize response
            details = {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "eps": info.get("trailingEps"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "description": info.get("longBusinessSummary", ""),
                "country": info.get("country", ""),
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", ""),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "average_volume": info.get("averageVolume"),
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "book_value": info.get("bookValue"),
                "price_to_book": info.get("priceToBook"),
                "debt_to_equity": info.get("debtToEquity"),
                "roe": info.get("returnOnEquity"),
                "revenue_growth": info.get("revenueGrowth"),
                "return_on_assets": info.get("returnOnAssets"),
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "gross_margin": info.get("grossMargins"),
                "raw_info": self._to_jsonable(info),
            }

            try:
                recommendations = getattr(ticker, "recommendations", None)
                if isinstance(recommendations, pd.DataFrame) and not recommendations.empty:
                    details["analyst_recommendations"] = self._df_to_records(recommendations)
            except Exception:
                pass

            try:
                sustainability = getattr(ticker, "sustainability", None)
                if isinstance(sustainability, pd.DataFrame) and not sustainability.empty:
                    details["sustainability"] = self._df_to_records(sustainability)
            except Exception:
                pass

            try:
                major_holders = getattr(ticker, "major_holders", None)
                if isinstance(major_holders, pd.DataFrame) and not major_holders.empty:
                    details["major_holders"] = self._df_to_records(major_holders)
            except Exception:
                pass

            try:
                institutional_holders = getattr(ticker, "institutional_holders", None)
                if isinstance(institutional_holders, pd.DataFrame) and not institutional_holders.empty:
                    details["institutional_holders"] = self._df_to_records(institutional_holders)
            except Exception:
                pass

            try:
                options = getattr(ticker, "options", None)
                if options is not None and len(options) > 0:
                    details["options_expirations"] = self._to_jsonable(list(options))
            except Exception:
                pass

            try:
                income_stmt = getattr(ticker, "income_stmt", None)
                if isinstance(income_stmt, pd.DataFrame) and not income_stmt.empty:
                    details["income_stmt_annual"] = self._df_to_records(income_stmt)
            except Exception:
                pass

            try:
                quarterly_income_stmt = getattr(ticker, "quarterly_income_stmt", None)
                if isinstance(quarterly_income_stmt, pd.DataFrame) and not quarterly_income_stmt.empty:
                    details["income_stmt_quarterly"] = self._df_to_records(quarterly_income_stmt)
            except Exception:
                pass

            return details
            
        except Exception as e:
            logger.error(f"Failed to fetch symbol details for {symbol}: {e}")
            raise
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamental financial data
        """
        try:
            # Get symbol details (includes many fundamentals)
            details = self.fetch_symbol_details(symbol)
            
            ticker = self._get_ticker(symbol)
            
            # Get financial statements
            financials = ticker.financials
            balance_sheet = ticker.balance_sheet
            cashflow = ticker.cashflow
            
            # Add recent financial data
            if not financials.empty:
                latest_financials = financials.iloc[:, 0]  # Most recent period
                details.update({
                    "revenue": latest_financials.get("Total Revenue"),
                    "gross_profit": latest_financials.get("Gross Profit"),
                    "operating_income": latest_financials.get("Operating Income"),
                    "net_income": latest_financials.get("Net Income"),
                    "total_assets": latest_financials.get("Total Assets"),
                    "total_liabilities": latest_financials.get("Total Liab"),
                })
            
            if not balance_sheet.empty:
                latest_balance = balance_sheet.iloc[:, 0]
                details.update({
                    "cash_and_equivalents": latest_balance.get("Cash And Cash Equivalents"),
                    "short_term_investments": latest_balance.get("Short Term Investments"),
                    "long_term_debt": latest_balance.get("Long Term Debt"),
                    "short_term_debt": latest_balance.get("Current Debt"),  # Updated: Current Debt is the correct field
                    "total_debt": latest_balance.get("Total Debt"),  # Added: Total Debt from Yahoo
                    "total_equity": latest_balance.get("Stockholders Equity"),  # Moved from financials to balance sheet
                    "property_plant_equipment": latest_balance.get("Net PPE"),
                })
            
            if not cashflow.empty:
                latest_cashflow = cashflow.iloc[:, 0]
                details.update({
                    "operating_cash_flow": latest_cashflow.get("Operating Cash Flow"),
                    "investing_cash_flow": latest_cashflow.get("Investing Cash Flow"),
                    "financing_cash_flow": latest_cashflow.get("Financing Cash Flow"),
                    "free_cash_flow": latest_cashflow.get("Operating Cash Flow") - latest_cashflow.get("Capital Expenditure"),
                })
            
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
                    earnings_data.append({
                        "symbol": symbol,
                        "earnings_date": earnings_date.strftime("%Y-%m-%d") if hasattr(earnings_date, 'strftime') else str(earnings_date),
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
    
    def fetch_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """
        Fetch earnings calendar data for multiple symbols and date range.
        Args:
            symbols: List of symbols (if None, fetches major indices)
            start_date: Start date in YYYY-MM-DD format (if None, uses today)
            end_date: End date in YYYY-MM-DD format (if None, uses start_date + 90 days)
        """
        try:
            # Yahoo doesn't have direct earnings calendar API, so we'll use earnings history + future estimates
            if not symbols:
                # Default to major symbols if none provided
                symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "JNJ", "V"]
            
            from datetime import datetime, timedelta
            if not start_date:
                start_date = datetime.now().strftime("%Y-%m-%d")
            if not end_date:
                end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
            
            earnings_data = []
            
            for symbol in symbols:
                try:
                    # Get earnings history (includes future estimates)
                    earnings_history = self.fetch_earnings(symbol)
                    symbol_info = self.fetch_symbol_details(symbol)
                    
                    for earnings in earnings_history:
                        earnings_date = earnings.get("earnings_date")
                        if earnings_date:
                            # Parse date and check if within range
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
                                        "earnings_date": earnings_date,
                                        "eps_estimate": earnings.get("eps_estimate"),
                                        "eps_actual": earnings.get("eps_actual"),
                                        "revenue_estimate": earnings.get("revenue_estimate"),
                                        "revenue_actual": earnings.get("revenue_actual"),
                                        "quarter": earnings.get("quarter"),
                                        "year": earnings.get("year"),
                                        "time": "After Market Close" if earnings_dt.hour >= 16 else "Before Market Open",
                                        "market_cap": symbol_info.get("marketCap"),
                                        "sector": symbol_info.get("sector"),
                                        "industry": symbol_info.get("industry")
                                    })
                            except (ValueError, TypeError):
                                continue
                                
                except Exception as e:
                    logger.warning(f"Failed to fetch earnings for {symbol}: {e}")
                    continue
            
            # Sort by date and symbol
            earnings_data.sort(key=lambda x: (x.get("earnings_date"), x.get("symbol")))
            
            logger.info(f"✅ Fetched {len(earnings_data)} earnings calendar entries")
            return earnings_data
            
        except Exception as e:
            logger.error(f"Failed to fetch earnings calendar: {e}")
            return []
    
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
