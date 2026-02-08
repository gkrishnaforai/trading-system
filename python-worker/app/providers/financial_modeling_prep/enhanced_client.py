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
        """Make HTTP request with rate limiting, retries, and error handling"""
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
            
            if isinstance(data, dict) and "historical" in data:
                return data
            return {"historical": []}
        except Exception as e:
            logger.error(f"❌ Error fetching historical prices for {symbol}: {e}")
            return {"historical": []}
    
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
        try:
            endpoint = "/stock-list"
            data = self._make_request(endpoint)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching stock list: {e}")
            return []
    
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
    
    def get_income_statement(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get income statement data"""
        try:
            endpoint = "/income-statement"
            params = {"symbol": symbol, "period": period}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching income statement for {symbol}: {e}")
            return []
    
    def get_balance_sheet_statement(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get balance sheet statement data"""
        try:
            endpoint = "/balance-sheet-statement"
            params = {"symbol": symbol, "period": period}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching balance sheet for {symbol}: {e}")
            return []
    
    def get_cash_flow_statement(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get cash flow statement data"""
        try:
            endpoint = "/cash-flow-statement"
            params = {"symbol": symbol, "period": period}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching cash flow statement for {symbol}: {e}")
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
    
    def get_key_metrics(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get key financial metrics"""
        try:
            endpoint = "/key-metrics"
            params = {"symbol": symbol, "period": period}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching key metrics for {symbol}: {e}")
            return []
    
    def get_financial_ratios(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get financial ratios"""
        try:
            endpoint = "/ratios"
            params = {"symbol": symbol, "period": period}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching financial ratios for {symbol}: {e}")
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
    
    def get_earning_transcript(self, symbol: str, year: int, quarter: int) -> List[Dict[str, Any]]:
        """Get specific earning call transcript"""
        try:
            endpoint = "/earning-call-transcript"
            params = {"symbol": symbol, "year": year, "quarter": quarter}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching earning transcript for {symbol} {year} Q{quarter}: {e}")
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
        """Get latest general news"""
        try:
            endpoint = "/news/general-latest"
            params = {"page": page, "limit": limit}
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
        """Get latest stock market news"""
        try:
            endpoint = "/news/stock-latest"
            params = {"page": page, "limit": limit}
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
        """Get stock grades"""
        try:
            endpoint = "/grades"
            params = {"symbol": symbol}
            data = self._make_request(endpoint, params)
            
            if isinstance(data, list):
                return data
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
    
    def get_comprehensive_financial_data(self, symbol: str, period: str = "annual") -> Dict[str, Any]:
        """Get comprehensive financial data for a symbol"""
        return {
            "profile": self.get_company_profile(symbol),
            "income_statement": self.get_income_statement(symbol, period),
            "balance_sheet": self.get_balance_sheet_statement(symbol, period),
            "cash_flow": self.get_cash_flow_statement(symbol, period),
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
enhanced_fmp_client = EnhancedFMPClient.from_settings()
