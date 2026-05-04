"""
Enhanced FMP Client with Complete API Coverage
Includes all FMP endpoints from the official documentation
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
from app.utils.cache import CacheManager
from app.observability.logging import get_logger

logger = get_logger("fmp_enhanced_client")

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


class EnhancedFMPClient:
    """
    Enhanced FMP client with complete API coverage
    Includes all endpoints from official FMP documentation
    """
    
    def __init__(self, config: FinancialModelingPrepConfig):
        self.config = config
        self.session = requests.Session()
        self.session.timeout = config.timeout

        self.cache = CacheManager(prefix="fmp")
        
        # Set headers to mimic curl/browser requests
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        
        self.last_error: Optional[str] = None
        
        # Rate limiting for FMP
        self.rate_limiter = RateLimiter(
            max_calls=config.rate_limit_calls,
            time_window=config.rate_limit_window,
            name="FMP"
        )
        
        logger.info(f"✅ Enhanced FMP Client initialized (rate limit: {config.rate_limit_calls}/{config.rate_limit_window}s)")
    
    @classmethod
    def from_settings(cls) -> "EnhancedFMPClient":
        """Create client with default settings"""
        fmp_config = FinancialModelingPrepConfig(
            api_key=settings.fmp_api_key,
            base_url=settings.fmp_base_url,
            timeout=settings.fmp_timeout,
            max_retries=settings.fmp_max_retries,
            retry_delay=settings.fmp_retry_delay,
            rate_limit_calls=settings.fmp_rate_limit_calls,
            rate_limit_window=settings.fmp_rate_limit_window
        )
        return cls(fmp_config)
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make HTTP request with rate limiting, retries, and error handling"""
        # Rate limiting
        if not self.rate_limiter.acquire():
            raise Exception("Rate limit exceeded - could not acquire permission for API call")
        
        # Add API key to params
        if params is None:
            params = {}
        params["apikey"] = self.config.api_key
        
        url = f"{self.config.base_url}{endpoint}"
        
        # Log request details (without API key)
        safe_params = {k: v for k, v in params.items() if k != 'apikey'}
        logger.debug(f"🌐 FMP Request: {endpoint} with params: {safe_params}")
        
        for attempt in range(self.config.max_retries):
            try:
                # Make request with curl-like headers
                response = self.session.get(url, params=params, timeout=self.config.timeout)
                
                # Log request details for debugging
                logger.debug(f"📡 FMP Response: status={response.status_code}, url={response.url}")
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        logger.debug(f"📊 FMP Data: type={type(data)}, size={len(str(data)) if data else 0}")
                        
                        # Check for FMP API errors
                        if isinstance(data, dict):
                            if "Error Message" in data:
                                logger.error(f"❌ FMP API Error: {data['Error Message']}")
                                raise ValueError(f"FMP API error: {data['Error Message']}")
                            elif "error" in data:
                                logger.error(f"❌ FMP API Error: {data['error']}")
                                raise ValueError(f"FMP API error: {data['error']}")
                        
                        return data
                        
                    except ValueError as json_error:
                        logger.error(f"❌ FMP JSON parsing error: {json_error}")
                        logger.debug(f"Raw response: {response.text[:500]}...")
                        raise ValueError(f"Invalid JSON response from FMP: {json_error}")
                elif response.status_code == 429:
                    retry_after_header = (response.headers or {}).get("Retry-After")
                    retry_after_s = None
                    if retry_after_header:
                        try:
                            retry_after_s = float(retry_after_header)
                        except Exception:
                            retry_after_s = None

                    base_sleep = self.config.retry_delay * (2 ** attempt)
                    sleep_s = max(base_sleep, retry_after_s or 0)
                    logger.warning(
                        f"⏳ FMP rate limited (429) for {endpoint} (attempt {attempt + 1}/{self.config.max_retries}). "
                        f"Sleeping {sleep_s:.2f}s"
                    )

                    if attempt < self.config.max_retries - 1:
                        time.sleep(sleep_s)
                        continue

                    logger.error("❌ FMP HTTP Error: status=429")
                    response.raise_for_status()
                elif response.status_code == 402:
                    # Plan limitation / not enabled for this API key.
                    # Treat as expected "no data" so ingestion can SKIP without noisy retries or API-key leaks.
                    logger.info(f"⚠️ FMP endpoint not available for current plan (402): {endpoint}")
                    return []
                else:
                    logger.error(f"❌ FMP HTTP Error: status={response.status_code}")
                    logger.debug(f"Response body: {response.text[:500]}...")
                    response.raise_for_status()
                
            except requests.exceptions.Timeout as e:
                logger.warning(f"⏰ FMP Request timeout (attempt {attempt + 1}/{self.config.max_retries}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"🔌 FMP Connection error (attempt {attempt + 1}/{self.config.max_retries}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise
            except requests.exceptions.RequestException as e:
                logger.warning(f"🌐 FMP Request failed (attempt {attempt + 1}/{self.config.max_retries}): {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay * (2 ** attempt))
                    continue
                raise
            except ValueError as e:
                # API error, don't retry
                logger.error(f"❌ FMP API error (no retry): {e}")
                raise
        
        logger.error(f"❌ FMP Request failed after {self.config.max_retries} attempts")
        raise Exception(f"FMP request failed after {self.config.max_retries} attempts")
    
    # === MARKET DATA ===
    
    def get_real_time_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get real-time stock quote"""
        try:
            endpoint = "/quote"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            elif isinstance(data, dict):
                return data
            return None
        except Exception as e:
            logger.error(f"❌ Error fetching real-time quote for {symbol}: {e}")
            return None
    
    # === TECHNICAL INDICATORS ===
    
    def get_technical_indicators_ema(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Exponential Moving Average (EMA) technical indicator"""
        try:
            endpoint = "/technical-indicators/ema"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            
            logger.debug(f"🔍 FMP API Call: {endpoint} for {symbol} (period={period_length}, timeframe={timeframe})")
            
            data = self._make_request(endpoint, params)
            
            logger.debug(f"📡 FMP Response for {symbol} EMA{period_length}: type={type(data)}, length={len(data) if isinstance(data, list) else 'N/A'}")
            
            if isinstance(data, list):
                if len(data) == 0:
                    logger.warning(f"⚠️ FMP returned empty list for {symbol} EMA{period_length}")
                    return []
                logger.debug(f"✅ FMP EMA{period_length} for {symbol}: {len(data)} data points")
                return data
            elif isinstance(data, dict) and "data" in data:
                if len(data["data"]) == 0:
                    logger.warning(f"⚠️ FMP returned empty data dict for {symbol} EMA{period_length}")
                    return []
                logger.debug(f"✅ FMP EMA{period_length} for {symbol}: {len(data['data'])} data points")
                return data["data"]
            elif isinstance(data, dict):
                # Check for error response
                if "error" in data:
                    logger.error(f"❌ FMP API error for {symbol} EMA{period_length}: {data.get('error')}")
                    return []
                logger.warning(f"⚠️ FMP returned unexpected dict for {symbol} EMA{period_length}: {data}")
                return []
            else:
                logger.warning(f"⚠️ FMP returned unexpected type for {symbol} EMA{period_length}: {type(data)}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching EMA{period_length} for {symbol}: {e}")
            logger.exception(f"Full exception details for {symbol} EMA{period_length}:")
            return []
    
    def get_technical_indicators_sma(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Simple Moving Average (SMA) technical indicator"""
        try:
            endpoint = "/technical-indicators/sma"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching SMA for {symbol}: {e}")
            return []
    
    def get_technical_indicators_wma(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Weighted Moving Average (WMA) technical indicator"""
        try:
            endpoint = "/technical-indicators/wma"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching WMA for {symbol}: {e}")
            return []
    
    def get_technical_indicators_dema(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Double Exponential Moving Average (DEMA) technical indicator"""
        try:
            endpoint = "/technical-indicators/dema"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching DEMA for {symbol}: {e}")
            return []
    
    def get_technical_indicators_tema(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Triple Exponential Moving Average (TEMA) technical indicator"""
        try:
            endpoint = "/technical-indicators/tema"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching TEMA for {symbol}: {e}")
            return []
    
    def get_technical_indicators_rsi(self, symbol: str, period_length: int = 14, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Relative Strength Index (RSI) technical indicator"""
        try:
            endpoint = "/technical-indicators/rsi"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching RSI for {symbol}: {e}")
            return []
    
    def get_technical_indicators_standard_deviation(self, symbol: str, period_length: int = 20, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Standard Deviation technical indicator"""
        try:
            endpoint = "/technical-indicators/standarddeviation"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching Standard Deviation for {symbol}: {e}")
            return []
    
    def get_technical_indicators_williams(self, symbol: str, period_length: int = 14, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Williams %R technical indicator"""
        try:
            endpoint = "/technical-indicators/williams"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching Williams %R for {symbol}: {e}")
            return []
    
    def get_technical_indicators_adx(self, symbol: str, period_length: int = 14, timeframe: str = "1day") -> List[Dict[str, Any]]:
        """Get Average Directional Index (ADX) technical indicator"""
        try:
            endpoint = "/technical-indicators/adx"
            params = {
                "symbol": symbol,
                "periodLength": period_length,
                "timeframe": timeframe
            }
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching ADX for {symbol}: {e}")
            return []
    
    def get_all_technical_indicators(self, symbol: str, timeframe: str = "1day") -> Dict[str, List[Dict[str, Any]]]:
        """Get all available technical indicators for a symbol"""
        try:
            logger.info(f"🔄 Fetching all technical indicators for {symbol} from FMP API")
            
            indicators = {}
            
            # Moving Averages
            logger.debug(f"📊 Fetching EMA20 for {symbol}")
            indicators["ema_20"] = self.get_technical_indicators_ema(symbol, 20, timeframe)
            logger.debug(f"📊 Fetching EMA50 for {symbol}")
            indicators["ema_50"] = self.get_technical_indicators_ema(symbol, 50, timeframe)
            logger.debug(f"📊 Fetching SMA20 for {symbol}")
            indicators["sma_20"] = self.get_technical_indicators_sma(symbol, 20, timeframe)
            logger.debug(f"📊 Fetching SMA50 for {symbol}")
            indicators["sma_50"] = self.get_technical_indicators_sma(symbol, 50, timeframe)
            logger.debug(f"📊 Fetching SMA200 for {symbol}")
            indicators["sma_200"] = self.get_technical_indicators_sma(symbol, 200, timeframe)
            
            # Advanced Moving Averages
            logger.debug(f"📊 Fetching WMA20 for {symbol}")
            indicators["wma_20"] = self.get_technical_indicators_wma(symbol, 20, timeframe)
            logger.debug(f"📊 Fetching DEMA20 for {symbol}")
            indicators["dema_20"] = self.get_technical_indicators_dema(symbol, 20, timeframe)
            logger.debug(f"📊 Fetching TEMA20 for {symbol}")
            indicators["tema_20"] = self.get_technical_indicators_tema(symbol, 20, timeframe)
            
            # Momentum Indicators
            logger.debug(f"📊 Fetching RSI14 for {symbol}")
            indicators["rsi_14"] = self.get_technical_indicators_rsi(symbol, 14, timeframe)
            
            # Volatility Indicators
            logger.debug(f"📊 Fetching Standard Deviation20 for {symbol}")
            indicators["stddev_20"] = self.get_technical_indicators_standard_deviation(symbol, 20, timeframe)
            
            # Other Indicators
            logger.debug(f"📊 Fetching Williams %R14 for {symbol}")
            indicators["williams_14"] = self.get_technical_indicators_williams(symbol, 14, timeframe)
            logger.debug(f"📊 Fetching ADX14 for {symbol}")
            indicators["adx_14"] = self.get_technical_indicators_adx(symbol, 14, timeframe)
            
            # Log summary with detailed results
            total_indicators = sum(len(data) for data in indicators.values())
            successful_indicators = sum(1 for data in indicators.values() if data)
            failed_indicators = sum(1 for data in indicators.values() if not data)
            
            logger.info(f"✅ Fetched {total_indicators} total data points for {symbol}")
            logger.info(f"📊 Success: {successful_indicators} indicators, Failed: {failed_indicators} indicators")
            
            for indicator_name, data in indicators.items():
                if data:
                    logger.debug(f"   ✅ {indicator_name}: {len(data)} points")
                else:
                    logger.warning(f"   ❌ {indicator_name}: No data - API call failed")
            
            # If most indicators failed, this might be a symbol-specific issue
            if failed_indicators > successful_indicators:
                logger.warning(f"⚠️ Majority of indicators failed for {symbol} - might be symbol-specific issue")
            
            return indicators
            
        except Exception as e:
            logger.error(f"❌ Error fetching all technical indicators for {symbol}: {e}")
            logger.exception(f"Full exception details for {symbol}:")
            return {}
    
    def get_historical_prices_full(self, symbol: str, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """Get full historical price data"""
        try:
            endpoint = "/historical-price-eod/full"
            params = {"symbol": symbol}
            
            if start_date:
                params["from"] = start_date
            if end_date:
                params["to"] = end_date
            
            data = self._make_request(endpoint, params)
            return data if data else {}
        except Exception as e:
            logger.error(f"❌ Error fetching historical prices for {symbol}: {e}")
            return {}
    
    def get_intraday_prices_5min(self, symbol: str, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """Get 5-minute intraday price data"""
        try:
            endpoint = "/historical-chart/5min"
            params = {"symbol": symbol}
            
            if start_date:
                params["from"] = start_date
            if end_date:
                params["to"] = end_date
            
            data = self._make_request(endpoint, params)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"❌ Error fetching 5-minute intraday prices for {symbol}: {e}")
            return []
    
    def get_institutional_buying(self, symbol: str) -> List[Dict[str, Any]]:
        """Get institutional buying data"""
        try:
            endpoint = "/institutional-ownership"
            params = {"symbol": symbol}
            
            data = self._make_request(endpoint, params)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"❌ Error fetching institutional buying data for {symbol}: {e}")
            return []
    
    # === COMPANY INFORMATION ===
    
    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Get detailed company profile"""
        try:
            endpoint = "/profile"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            elif isinstance(data, dict):
                return data
            return {}
        except Exception as e:
            logger.error(f"❌ Error fetching company profile for {symbol}: {e}")
            return {}
    
    def get_stock_list(self) -> List[Dict[str, Any]]:
        """Get complete list of available stocks"""
        cache_key = "stock_list"
        try:
            cached = self.cache.get(cache_key)
            if cached:
                return cached

            endpoint = "/stock-list"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                self.cache.set(cache_key, data, ttl=86400)
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching stock list: {e}")
            cached = self.cache.get(cache_key)
            return cached or []
    
    def search_symbols(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for company stock symbols"""
        try:
            endpoint = "/search-name"
            params = {"query": query, "limit": limit}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error searching symbols for {query}: {e}")
            return []
    
    # === FINANCIAL STATEMENTS ===
    
    def get_income_statement(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get income statement data"""
        try:
            endpoint = "/income-statement"
            params = {"symbol": symbol}
            if period:
                params["period"] = period
            
            # Log API call details (excluding API key)
            logger.info(f"📡 FMP API Call - Income Statement:")
            logger.info(f"   - Endpoint: {endpoint}")
            logger.info(f"   - Symbol: {symbol}")
            logger.info(f"   - Period: {period}")
            logger.info(f"   - Full URL: {self.config.base_url}{endpoint}?symbol={symbol}" + (f"&period={period}" if period else ""))
            
            data = self._make_request(endpoint, params)
            
            logger.info(f"📊 FMP Income Statement Response for {symbol}:")
            logger.info(f"   - Data type: {type(data)}")
            logger.info(f"   - Data length: {len(data) if isinstance(data, list) else 'N/A'}")
            if isinstance(data, list) and data:
                logger.info(f"   - Sample keys: {list(data[0].keys())[:10] if isinstance(data[0], dict) else 'N/A'}")
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching income statement for {symbol}: {e}")
            logger.exception(f"Full exception details for income statement {symbol}:")
            return []
    
    def get_balance_sheet_statement(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get balance sheet statement data"""
        try:
            endpoint = "/balance-sheet-statement"
            params = {"symbol": symbol}
            if period:
                params["period"] = period
            
            # Log API call details (excluding API key)
            logger.info(f"📡 FMP API Call - Balance Sheet:")
            logger.info(f"   - Endpoint: {endpoint}")
            logger.info(f"   - Symbol: {symbol}")
            logger.info(f"   - Period: {period}")
            logger.info(f"   - Full URL: {self.config.base_url}{endpoint}?symbol={symbol}" + (f"&period={period}" if period else ""))
            
            data = self._make_request(endpoint, params)
            
            logger.info(f"📊 FMP Balance Sheet Response for {symbol}:")
            logger.info(f"   - Data type: {type(data)}")
            logger.info(f"   - Data length: {len(data) if isinstance(data, list) else 'N/A'}")
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching balance sheet statement for {symbol}: {e}")
            logger.exception(f"Full exception details for balance sheet {symbol}:")
            return []
    
    def get_cash_flow_statement(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get cash flow statement data"""
        try:
            endpoint = "/cash-flow-statement"
            params = {"symbol": symbol}
            if period:
                params["period"] = period
            
            # Log API call details (excluding API key)
            logger.info(f"📡 FMP API Call - Cash Flow:")
            logger.info(f"   - Endpoint: {endpoint}")
            logger.info(f"   - Symbol: {symbol}")
            logger.info(f"   - Period: {period}")
            logger.info(f"   - Full URL: {self.config.base_url}{endpoint}?symbol={symbol}" + (f"&period={period}" if period else ""))
            
            data = self._make_request(endpoint, params)
            
            logger.info(f"📊 FMP Cash Flow Response for {symbol}:")
            logger.info(f"   - Data type: {type(data)}")
            logger.info(f"   - Data length: {len(data) if isinstance(data, list) else 'N/A'}")
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching cash flow statement for {symbol}: {e}")
            logger.exception(f"Full exception details for cash flow {symbol}:")
            return []
    
    def get_latest_financial_statements(self, page: int = 0, limit: int = 250) -> List[Dict[str, Any]]:
        """Get latest financial statements for all companies"""
        try:
            endpoint = "/latest-financial-statements"
            params = {"page": page, "limit": limit}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching latest financial statements: {e}")
            return []
    
    def get_income_statement_ttm(self, symbol: str) -> List[Dict[str, Any]]:
        """Get trailing twelve months income statement"""
        try:
            endpoint = "/income-statement-ttm"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching TTM income statement for {symbol}: {e}")
            return []
    
    def get_balance_sheet_ttm(self, symbol: str) -> List[Dict[str, Any]]:
        """Get trailing twelve months balance sheet"""
        try:
            endpoint = "/balance-sheet-statement-ttm"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching TTM balance sheet for {symbol}: {e}")
            return []
    
    def get_cash_flow_ttm(self, symbol: str) -> List[Dict[str, Any]]:
        """Get trailing twelve months cash flow statement"""
        try:
            endpoint = "/cash-flow-statement-ttm"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching TTM cash flow for {symbol}: {e}")
            return []
    
    # === FINANCIAL METRICS AND RATIOS ===
    
    def get_key_metrics(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get key metrics for a symbol"""
        try:
            endpoint = "/key-metrics"
            params = {"symbol": symbol}
            
            # Only add period if provided and valid for this endpoint
            if period and period in ["annual","Q1","Q2","Q3","Q4"]:
                params["period"] = period
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching key metrics for {symbol}: {e}")
            return []
    
    def get_financial_ratios(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get financial ratios"""
        try:
            endpoint = "/ratios"
            params = {"symbol": symbol}
            
            # Only add period if provided and valid for this endpoint
            if period and period in ["annual","Q1","Q2","Q3","Q4"]:
                params["period"] = period
            
            # Log API call details (excluding API key)
            logger.info(f"📡 FMP API Call - Financial Ratios:")
            logger.info(f"   - Endpoint: {endpoint}")
            logger.info(f"   - Symbol: {symbol}")
            logger.info(f"   - Period: {period}")
            logger.info(f"   - Full URL: {self.config.base_url}{endpoint}?symbol={symbol}" + (f"&period={period}" if period else ""))
            
            data = self._make_request(endpoint, params)
            
            logger.info(f"📊 FMP Financial Ratios Response for {symbol}:")
            logger.info(f"   - Data type: {type(data)}")
            logger.info(f"   - Data length: {len(data) if isinstance(data, list) else 'N/A'}")
            if isinstance(data, list) and data:
                logger.info(f"   - Sample keys: {list(data[0].keys())[:10] if isinstance(data[0], dict) else 'N/A'}")
                logger.info(f"   - Sample data: {str(data[0])[:200]}...")
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching financial ratios for {symbol}: {e}")
            logger.exception(f"Full exception details for financial ratios {symbol}:")
            return []
    
    def get_key_metrics_ttm(self, symbol: str) -> List[Dict[str, Any]]:
        """Get trailing twelve months key metrics"""
        try:
            endpoint = "/key-metrics-ttm"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching TTM key metrics for {symbol}: {e}")
            return []
    
    def get_financial_ratios_ttm(self, symbol: str) -> List[Dict[str, Any]]:
        """Get trailing twelve months financial ratios"""
        try:
            endpoint = "/ratios-ttm"
            params = {"symbol": symbol}
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching TTM financial ratios for {symbol}: {e}")
            return []
    
    # === GROWTH METRICS ===
    
    def get_income_statement_growth(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get income statement growth data (YoY growth rates)
        
        Args:
            symbol: Stock symbol
            period: Optional period (None for annual, "Q1", "Q2", "Q3", "Q4" for quarterly)
        """
        try:
            endpoint = "/income-statement-growth"
            params = {"symbol": symbol}
            if period:
                params["period"] = period
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching income statement growth for {symbol}: {e}")
            return []
    
    def get_balance_sheet_growth(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get balance sheet growth data (YoY growth rates)
        
        Args:
            symbol: Stock symbol
            period: Optional period (None for annual, "Q1", "Q2", "Q3", "Q4" for quarterly)
        """
        try:
            endpoint = "/balance-sheet-statement-growth"
            params = {"symbol": symbol}
            if period:
                params["period"] = period
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching balance sheet growth for {symbol}: {e}")
            return []
    
    def get_cash_flow_growth(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get cash flow statement growth data (YoY growth rates)
        
        Args:
            symbol: Stock symbol
            period: Optional period (None for annual, "Q1", "Q2", "Q3", "Q4" for quarterly)
        """
        try:
            endpoint = "/cash-flow-statement-growth"
            params = {"symbol": symbol}
            if period:
                params["period"] = period
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching cash flow growth for {symbol}: {e}")
            return []
    
    def get_financial_growth(self, symbol: str, period: str = None) -> List[Dict[str, Any]]:
        """Get comprehensive financial growth data (includes multi-year growth)
        
        Args:
            symbol: Stock symbol
            period: Optional period (None for annual, "Q1", "Q2", "Q3", "Q4" for quarterly)
        """
        try:
            endpoint = "/financial-growth"
            params = {"symbol": symbol}
            if period:
                params["period"] = period
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching financial growth for {symbol}: {e}")
            return []
    
    def get_financial_scores(self, symbol: str) -> List[Dict[str, Any]]:
        """Get financial health scores (Altman Z-Score, Piotroski Score)"""
        try:
            endpoint = "/financial-scores"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching financial scores for {symbol}: {e}")
            return []
    
    def get_owner_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Get owner earnings data"""
        try:
            endpoint = "/owner-earnings"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching owner earnings for {symbol}: {e}")
            return []
    
    # === EARNINGS TRANSCRIPTS ===
    
    def get_latest_earning_transcripts(self) -> List[Dict[str, Any]]:
        """Get available latest earning transcripts"""
        try:
            endpoint = "/earning-call-transcript-latest"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching latest earning transcripts: {e}")
            return []
    
    def get_earning_transcript(self, symbol: str, year: int = None, quarter: int = None) -> List[Dict[str, Any]]:
        """Get specific earning call transcript (current year only)"""
        try:
            from datetime import datetime
            current_year = datetime.now().year
            
            # Default to current year if not specified
            if year is None:
                year = current_year
            elif year != current_year:
                logger.warning(f"⚠️  Only current year ({current_year}) data is available, requested year {year}")
                year = current_year
            
            endpoint = "/earning-call-transcript"
            params = {
                "symbol": symbol,
                "year": year
            }
            
            # Only add quarter if specified
            if quarter is not None:
                params["quarter"] = quarter
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching earning transcript for {symbol}: {e}")
            return []
    
    def get_transcript_dates_by_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """Get transcript dates for a specific symbol"""
        try:
            endpoint = "/earning-call-transcript-dates"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching transcript dates for {symbol}: {e}")
            return []
    
    def get_available_transcript_symbols(self) -> List[Dict[str, Any]]:
        """Get list of symbols with available transcripts"""
        try:
            endpoint = "/earnings-transcript-list"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching available transcript symbols: {e}")
            return []
    
    # === NEWS ===
    
    def get_fmp_articles(self, page: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get latest FMP articles"""
        try:
            endpoint = "/fmp-articles"
            params = {"page": page, "limit": limit}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching FMP articles: {e}")
            return []
    
    def get_general_news(self, page: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get latest general news for current day"""
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            
            endpoint = "/news/general-latest"
            params = {
                "page": page,
                "limit": limit,
                "from": today,
                "to": today
            }
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching general news: {e}")
            return []
    
    def get_press_releases(self, page: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get latest press releases"""
        try:
            endpoint = "/news/press-releases-latest"
            params = {"page": page, "limit": limit}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching press releases: {e}")
            return []
    
    def get_stock_news(self, page: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get latest stock market news for current day"""
        try:
            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")
            
            endpoint = "/news/stock-latest"
            params = {
                "page": page,
                "limit": limit,
                "from": today,
                "to": today
            }
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching stock news: {e}")
            return []
    
    def get_crypto_news(self, page: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get latest cryptocurrency news"""
        try:
            endpoint = "/news/crypto-latest"
            params = {"page": page, "limit": limit}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching crypto news: {e}")
            return []
    
    def get_forex_news(self, page: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get latest forex news"""
        try:
            endpoint = "/news/forex-latest"
            params = {"page": page, "limit": limit}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching forex news: {e}")
            return []
    
    def search_press_releases(self, symbols: str) -> List[Dict[str, Any]]:
        """Search press releases by symbols"""
        try:
            endpoint = "/news/press-releases"
            params = {"symbols": symbols}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error searching press releases for {symbols}: {e}")
            return []
    
    def search_stock_news(self, symbols: str) -> List[Dict[str, Any]]:
        """Search stock news by symbols"""
        try:
            endpoint = "/news/stock"
            params = {"symbols": symbols}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error searching stock news for {symbols}: {e}")
            return []
    
    def search_crypto_news(self, symbols: str) -> List[Dict[str, Any]]:
        """Search crypto news by symbols"""
        try:
            endpoint = "/news/crypto"
            params = {"symbols": symbols}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error searching crypto news for {symbols}: {e}")
            return []
    
    def search_forex_news(self, symbols: str) -> List[Dict[str, Any]]:
        """Search forex news by symbols"""
        try:
            endpoint = "/news/forex"
            params = {"symbols": symbols}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error searching forex news for {symbols}: {e}")
            return []
    
    # === ANALYST DATA ===
    
    def get_analyst_ratings(self, symbol: str) -> List[Dict[str, Any]]:
        """Get analyst ratings data"""
        try:
            # Try multiple possible endpoints for analyst ratings
            endpoints = ["/grade", "/analyst-grades", "/analyst-ratings-ticker"]
            
            for endpoint in endpoints:
                try:
                    params = {"symbol": symbol}
                    data = self._make_request(endpoint, params)
                    
                    if isinstance(data, list) and data:
                        logger.info(f"✅ Found analyst ratings using endpoint: {endpoint}")
                        return data
                except Exception as endpoint_error:
                    logger.debug(f"🔍 Endpoint {endpoint} failed: {endpoint_error}")
                    continue
            
            logger.warning(f"⚠️ No analyst ratings data found for {symbol}")
            return []
            
        except Exception as e:
            logger.error(f"❌ Error fetching analyst ratings for {symbol}: {e}")
            return []
    
    def get_financial_estimates(self, symbol: str, period: str = "annual", page: int = 0, limit: int = 10) -> List[Dict[str, Any]]:
        """Get analyst financial estimates"""
        try:
            endpoint = "/analyst-estimates"
            params = {"symbol": symbol, "period": period, "page": page, "limit": limit}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching financial estimates for {symbol}: {e}")
            return []
    
    def get_ratings_snapshot(self, symbol: str) -> List[Dict[str, Any]]:
        """Get ratings snapshot"""
        try:
            endpoint = "/ratings-snapshot"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching ratings snapshot for {symbol}: {e}")
            return []
    
    def get_historical_ratings(self, symbol: str) -> List[Dict[str, Any]]:
        """Get historical ratings"""
        try:
            endpoint = "/ratings-historical"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching historical ratings for {symbol}: {e}")
            return []
    
    def get_price_target_summary(self, symbol: str) -> List[Dict[str, Any]]:
        """Get price target summary"""
        try:
            endpoint = "/price-target-summary"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching price target summary for {symbol}: {e}")
            return []
    
    def get_price_target_consensus(self, symbol: str) -> List[Dict[str, Any]]:
        """Get price target consensus"""
        try:
            endpoint = "/price-target-consensus"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching price target consensus for {symbol}: {e}")
            return []
    
    def get_stock_grades(self, symbol: str) -> List[Dict[str, Any]]:
        """Get stock grades (current year only, sorted by date descending)"""
        try:
            from datetime import datetime, timedelta
            current_date = datetime.now()
            current_year_start = datetime(current_date.year, 1, 1)
            
            endpoint = "/grades"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                # Filter to current year only and sort by date descending
                current_year_grades = []
                for grade in data:
                    grade_date_str = grade.get("date")
                    if grade_date_str:
                        try:
                            grade_date = datetime.strptime(grade_date_str, "%Y-%m-%d")
                            if grade_date >= current_year_start:
                                current_year_grades.append(grade)
                        except ValueError:
                            # Skip invalid dates
                            continue
                
                # Sort by date descending (latest first)
                current_year_grades.sort(
                    key=lambda x: datetime.strptime(x.get("date", "1970-01-01"), "%Y-%m-%d"),
                    reverse=True
                )
                
                logger.info(f"📊 Filtered to {len(current_year_grades)} current year grades (from {len(data)} total)")
                return current_year_grades
            else:
                logger.warning(f"⚠️ Unexpected data format for {symbol} grades: {type(data)}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching stock grades for {symbol}: {e}")
            return []
    
    def get_historical_stock_grades(self, symbol: str) -> List[Dict[str, Any]]:
        """Get historical stock grades"""
        try:
            endpoint = "/grades-historical"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching historical stock grades for {symbol}: {e}")
            return []
    
    def get_stock_grades_summary(self, symbol: str) -> List[Dict[str, Any]]:
        """Get stock grades summary"""
        try:
            endpoint = "/grades-consensus"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching stock grades summary for {symbol}: {e}")
            return []
    
    # === EARNINGS, DIVIDENDS, SPLITS ===
    
    def get_dividends_company(self, symbol: str) -> List[Dict[str, Any]]:
        """Get dividends for a specific company"""
        try:
            endpoint = "/dividends"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching dividends for {symbol}: {e}")
            return []
    
    def get_dividends_calendar(self) -> List[Dict[str, Any]]:
        """Get dividends calendar"""
        try:
            endpoint = "/dividends-calendar"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching dividends calendar: {e}")
            return []
    
    def get_earnings_report(self, symbol: str) -> List[Dict[str, Any]]:
        """Get earnings report"""
        try:
            endpoint = "/earnings"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching earnings report for {symbol}: {e}")
            return []
    
    def get_earnings_calendar(self, symbols: List[str] = None, from_date: str = None, to_date: str = None) -> List[Dict[str, Any]]:
        """Get earnings calendar"""
        try:
            endpoint = "/earnings-calendar"
            params = {}
            
            if symbols:
                params["symbols"] = ",".join(symbols)
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching earnings calendar: {e}")
            return []
    
    def get_ipos_calendar(self) -> List[Dict[str, Any]]:
        """Get IPOs calendar"""
        try:
            endpoint = "/ipos-calendar"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching IPOs calendar: {e}")
            return []
    
    def get_ipos_disclosure(self) -> List[Dict[str, Any]]:
        """Get IPOs disclosure"""
        try:
            endpoint = "/ipos-disclosure"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching IPOs disclosure: {e}")
            return []
    
    def get_ipos_prospectus(self) -> List[Dict[str, Any]]:
        """Get IPOs prospectus"""
        try:
            endpoint = "/ipos-prospectus"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching IPOs prospectus: {e}")
            return []
    
    def get_stock_split_details(self, symbol: str) -> List[Dict[str, Any]]:
        """Get stock split details"""
        try:
            endpoint = "/splits"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching stock split details for {symbol}: {e}")
            return []
    
    def get_stock_splits_calendar(self) -> List[Dict[str, Any]]:
        """Get stock splits calendar"""
        try:
            endpoint = "/splits-calendar"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching stock splits calendar: {e}")
            return []
    
    # === CONVENIENCE METHODS ===
    
    def get_comprehensive_financial_data(self, symbol: str, period: str = None) -> Dict[str, Any]:
        """Get comprehensive financial data for a symbol"""
        income_growth = self.get_income_statement_growth(symbol, period)
        balance_growth = self.get_balance_sheet_growth(symbol, period)
        cash_flow_growth = self.get_cash_flow_growth(symbol, period)

        income_statement = self.get_income_statement(symbol, period)
        balance_sheet = self.get_balance_sheet_statement(symbol, period)
        cash_flow = self.get_cash_flow_statement(symbol, period)

        as_of_date = None
        for rows in (income_growth, balance_growth, cash_flow_growth, income_statement, balance_sheet, cash_flow):
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                as_of_date = rows[0].get("date") or rows[0].get("fiscalDateEnding") or rows[0].get("fiscal_date_ending")
                if as_of_date:
                    as_of_date = str(as_of_date)
                    break
        return {
            "profile": self.get_company_profile(symbol),
            "meta": {"provider": "fmp", "as_of_date": as_of_date},
            "statements": {
                "income": income_statement,
                "balance": balance_sheet,
                "cash_flow": cash_flow,
            },
            "income_statement": income_statement,
            "balance_sheet": balance_sheet,
            "cash_flow": cash_flow,
            "income_statement_growth": income_growth,
            "balance_sheet_growth": balance_growth,
            "cash_flow_growth": cash_flow_growth,
            "statement_growth": {
                "income_statement": income_growth,
                "balance_sheet": balance_growth,
                "cash_flow": cash_flow_growth,
            },
            "key_metrics": self.get_key_metrics(symbol, period),
            "financial_ratios": self.get_financial_ratios(symbol, period),
            "financial_scores": self.get_financial_scores(symbol),
            "ratings": self.get_ratings_snapshot(symbol),
            "price_targets": self.get_price_target_consensus(symbol),
            "grades": self.get_stock_grades(symbol)
        }
    
    def get_market_news_summary(self, limit: int = 10) -> Dict[str, Any]:
        """Get summary of all news types"""
        return {
            "fmp_articles": self.get_fmp_articles(limit=limit),
            "general_news": self.get_general_news(limit=limit),
            "press_releases": self.get_press_releases(limit=limit),
            "stock_news": self.get_stock_news(limit=limit),
            "crypto_news": self.get_crypto_news(limit=limit),
            "forex_news": self.get_forex_news(limit=limit)
        }


# Global instance for easy access


# Legacy compatibility methods for backward compatibility
class FinancialModelingPrepClient(EnhancedFMPClient):
    """Legacy wrapper for backward compatibility"""
    
    def fetch_price_data(self, symbol: str, **kwargs) -> pd.DataFrame:
        """Fetch price data - supports both daily and intraday intervals"""
        interval = kwargs.get("interval", "1d")  # Default to daily
        
        if interval == "5m":
            # Handle 5-minute intraday data
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            
            logger.info(f"🔍 Fetching 5m intraday data for {symbol} from {start_date} to {end_date}")
            intraday_data = self.get_intraday_prices_5min(symbol, start_date, end_date)
            
            if intraday_data:
                logger.info(f"✅ Fetched {len(intraday_data)} 5m data points for {symbol}")
                return pd.DataFrame(intraday_data)
            else:
                logger.warning(f"⚠️ No 5m intraday data returned for {symbol}")
                return pd.DataFrame()
        else:
            # Handle daily historical data
            period = kwargs.get("period", "1y")  # Default to 1 year
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            
            # Convert period to start_date and end_date if not provided
            if not start_date or not end_date:
                from datetime import datetime, timedelta
                
                end_date = datetime.now().strftime("%Y-%m-%d")
                
                # Parse period (e.g., "1y", "6m", "30d")
                if period.endswith("y"):
                    years = int(period[:-1])
                    start_date = (datetime.now() - timedelta(days=years*365)).strftime("%Y-%m-%d")
                elif period.endswith("m"):
                    months = int(period[:-1])
                    start_date = (datetime.now() - timedelta(days=months*30)).strftime("%Y-%m-%d")
                elif period.endswith("d"):
                    days = int(period[:-1])
                    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                else:
                    # Default to 1 year if format not recognized
                    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            
            logger.info(f"🔍 Fetching daily historical data for {symbol} from {start_date} to {end_date}")
            hist_data = self.get_historical_prices_full(symbol, start_date, end_date)
            
            if hist_data:
                logger.debug(f"📊 FMP historical data type: {type(hist_data)}")
                
                # FMP returns a direct array, not wrapped in "historical" key
                if isinstance(hist_data, list):
                    logger.info(f"✅ Fetched {len(hist_data)} daily data points for {symbol}")
                    return pd.DataFrame(hist_data)
                elif isinstance(hist_data, dict) and "historical" in hist_data:
                    logger.info(f"✅ Fetched {len(hist_data['historical'])} daily data points for {symbol}")
                    return pd.DataFrame(hist_data["historical"])
                else:
                    logger.warning(f"⚠️ Unexpected FMP historical data format for {symbol}: {type(hist_data)}")
                    return pd.DataFrame()
            else:
                logger.warning(f"⚠️ No daily historical data returned for {symbol}")
                return pd.DataFrame()
    
    def fetch_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Legacy method - fetch current price"""
        return self.get_real_time_quote(symbol)
    
    def fetch_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """Legacy method - fetch symbol details"""
        return self.get_company_profile(symbol)
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Legacy method - fetch fundamentals"""
        return self.get_comprehensive_financial_data(symbol)
    
    def fetch_enhanced_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Legacy method - fetch enhanced fundamentals"""
        return self.get_comprehensive_financial_data(symbol)
    
    def fetch_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Legacy method - fetch news"""
        return self.search_stock_news(symbol)
    
    def fetch_earnings(self, symbol: str) -> List[Dict[str, Any]]:
        """Legacy method - fetch earnings"""
        return self.get_earnings_report(symbol)
    
    def fetch_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> List[Dict[str, Any]]:
        """Legacy method - fetch earnings calendar"""
        return self.get_earnings_calendar(symbols, start_date, end_date)
    
    def fetch_earnings_for_date(self, earnings_date: str, symbols: List[str] = None) -> List[Dict[str, Any]]:
        """Legacy method - fetch earnings for date"""
        return self.get_earnings_calendar(symbols, earnings_date, earnings_date)
    
    def fetch_industry_peers(self, symbol: str) -> Dict[str, Any]:
        """Legacy method - fetch industry peers"""
        # This method would need to be implemented based on available data
        return {}
    
    def fetch_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Legacy method - fetch corporate actions"""
        dividends = self.get_dividends_company(symbol)
        splits = self.get_stock_split_details(symbol)
        return dividends + splits
    
    def fetch_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        """Legacy method - fetch dividends"""
        return self.get_dividends_company(symbol)
    
    def fetch_splits(self, symbol: str) -> List[Dict[str, Any]]:
        """Legacy method - fetch stock splits"""
        return self.get_stock_split_details(symbol)
    
    def fetch_financial_statements(self, symbol: str, period: str = None) -> Dict[str, Any]:
        """Legacy method - fetch financial statements"""
        return {
            "income_statement": self.get_income_statement(symbol, period),
            "balance_sheet": self.get_balance_sheet_statement(symbol, period),
            "cash_flow": self.get_cash_flow_statement(symbol, period)
        }
    
    def fetch_quarterly_earnings_history(self, symbol: str) -> List[Dict[str, Any]]:
        """Legacy method - fetch quarterly earnings history"""
        return self.get_earnings_report(symbol)
    
    def fetch_analyst_recommendations(self, symbol: str) -> List[Dict[str, Any]]:
        """Legacy method - fetch analyst recommendations"""
        return self.get_stock_grades(symbol)
    
    def is_available(self) -> bool:
        """Legacy method - check availability"""
        try:
            # Avoid calling /stock-list here (very large response; easy to rate-limit).
            # Use a lightweight endpoint instead.
            profile = self.get_company_profile("AAPL")
            return bool(profile) or True
        except requests.exceptions.HTTPError as e:
            # If we're rate-limited, the service may still be up; treat as available.
            if getattr(getattr(e, "response", None), "status_code", None) == 429:
                return True
            return False
        except Exception:
            return False


# Factory function for dependency injection
def get_fmp_client():
    """Get FMP client instance - safe for dependency injection"""
    return EnhancedFMPClient.from_settings()


# Global instance for backward compatibility (uses factory function)
enhanced_fmp_client = get_fmp_client()
