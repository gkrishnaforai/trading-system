"""
Optimized FMP Data Loader
Efficiently loads data using FMP APIs with smart caching and on-demand loading
- Real-time prices: Always loaded from FMP
- Detailed data: Loaded on-demand with caching
- Bulk operations: Optimized for minimal API calls
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
import pandas as pd
from dataclasses import dataclass
from enum import Enum

from app.providers.financial_modeling_prep.client import enhanced_fmp_client
from app.database import db
from app.observability.logging import get_logger
from app.utils.cache import CacheManager

logger = get_logger("optimized_fmp_loader")


class DataType(Enum):
    """Data types with different loading strategies"""
    REAL_TIME_PRICE = "real_time_price"
    HISTORICAL_PRICES = "historical_prices"
    COMPANY_PROFILE = "company_profile"
    FINANCIALS = "financials"
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    KEY_METRICS = "key_metrics"
    FINANCIAL_RATIOS = "financial_ratios"
    FINANCIAL_SCORES = "financial_scores"
    ANALYST_RATINGS = "analyst_ratings"
    PRICE_TARGETS = "price_targets"
    STOCK_GRADES = "stock_grades"
    STOCK_LIST = "stock_list"
    SYMBOL_SEARCH = "symbol_search"
    MARKET_NEWS = "market_news"
    EARNINGS_TRANSCRIPTS = "earnings_transcripts"


@dataclass
class LoadStrategy:
    """Loading strategy for different data types"""
    cache_ttl: int  # Time to cache in seconds
    batch_size: int  # How many to load at once
    on_demand: bool  # Load only when requested
    priority: int  # Lower number = higher priority


# Loading strategies for different data types
LOAD_STRATEGIES = {
    DataType.REAL_TIME_PRICE.value: LoadStrategy(
        cache_ttl=60,      # Cache for 1 minute (real-time data)
        batch_size=1,      # One at a time for real-time
        on_demand=False,   # Always load real-time prices
        priority=1
    ),
    DataType.HISTORICAL_PRICES.value: LoadStrategy(
        cache_ttl=86400,  # Cache for 24 hours
        batch_size=5,      # Load 5 symbols at once
        on_demand=False,   # Load during bulk operations
        priority=2
    ),
    DataType.COMPANY_PROFILE.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=10,     # Load 10 profiles at once
        on_demand=True,    # Load only when requested
        priority=3
    ),
    DataType.INCOME_STATEMENT.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=4
    ),
    DataType.BALANCE_SHEET.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=5
    ),
    DataType.CASH_FLOW.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=6
    ),
    DataType.KEY_METRICS.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=7
    ),
    DataType.FINANCIAL_RATIOS.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=8
    ),
    DataType.FINANCIAL_SCORES.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=9
    ),
    DataType.ANALYST_RATINGS.value: LoadStrategy(
        cache_ttl=3600,    # Cache for 1 hour (analyst data changes frequently)
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=10
    ),
    DataType.PRICE_TARGETS.value: LoadStrategy(
        cache_ttl=3600,    # Cache for 1 hour
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=11
    ),
    DataType.STOCK_GRADES.value: LoadStrategy(
        cache_ttl=3600,    # Cache for 1 hour
        batch_size=5,      # Load 5 at once
        on_demand=True,    # Load only when requested
        priority=12
    ),
    DataType.MARKET_NEWS.value: LoadStrategy(
        cache_ttl=1800,    # Cache for 30 minutes
        batch_size=1,      # Load one at a time
        on_demand=True,    # Load only when requested
        priority=13
    ),
    DataType.EARNINGS_TRANSCRIPTS.value: LoadStrategy(
        cache_ttl=86400,   # Cache for 24 hours (transcripts don't change)
        batch_size=1,      # Load one at a time
        on_demand=True,    # Load only when requested
        priority=14
    ),
    DataType.STOCK_LIST.value: LoadStrategy(
        cache_ttl=86400,   # Cache for 24 hours
        batch_size=1,      # Single operation
        on_demand=False,   # Load during initialization
        priority=15
    ),
    DataType.SYMBOL_SEARCH.value: LoadStrategy(
        cache_ttl=3600,    # Cache for 1 hour
        batch_size=1,      # Single search
        on_demand=True,    # Always on-demand
        priority=16
    ),
    DataType.FINANCIALS.value: LoadStrategy(
        cache_ttl=604800,  # Cache for 7 days
        batch_size=5,      # Load 5 financials at once
        on_demand=True,    # Load only when requested
        priority=17
    )
}


class OptimizedFMPLoader:
    """Optimized FMP data loader with smart caching and on-demand loading"""
    
    def __init__(self, client: Optional[Any] = None):
        self.client = client or enhanced_fmp_client
        self.cache = CacheManager(prefix="fmp")
        self._stock_list_cache: Optional[List[Dict[str, Any]]] = None
        self._stock_list_cache_time: Optional[datetime] = None
        
        logger.info("✅ Optimized FMP Loader initialized")
    
    # === CORE API METHODS ===
    
    def search_symbol(self, query: str) -> List[Dict[str, Any]]:
        """Search for company stock symbols"""
        cache_key = f"search:{query.lower()}"
        strategy = LOAD_STRATEGIES[DataType.SYMBOL_SEARCH]
        
        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for symbol search: {query}")
            return cached
        
        try:
            logger.info(f"🔍 Searching for symbol: {query}")
            endpoint = "/search-name"
            params = {"query": query, "limit": 10}
            
            data = self.client._make_request(endpoint, params)
            results = data if isinstance(data, list) else []
            
            # Cache the results
            self.cache.set(cache_key, results, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Found {len(results)} symbols for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error searching symbols for {query}: {e}")
            return []
    
    def get_stock_list(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get complete list of available stocks (cached)"""
        strategy = LOAD_STRATEGIES[DataType.STOCK_LIST]
        
        # Check cache and refresh if needed
        if (not force_refresh and 
            self._stock_list_cache and 
            self._stock_list_cache_time and 
            (datetime.now() - self._stock_list_cache_time).seconds < strategy.cache_ttl):
            logger.debug("🎯 Using cached stock list")
            return self._stock_list_cache
        
        try:
            logger.info("📋 Fetching complete stock list from FMP")
            endpoint = "/stock-list"
            
            data = self.client._make_request(endpoint)
            stock_list = data if isinstance(data, list) else []
            
            # Update cache
            self._stock_list_cache = stock_list
            self._stock_list_cache_time = datetime.now()
            
            logger.info(f"✅ Loaded {len(stock_list)} stocks from FMP")
            return stock_list
            
        except Exception as e:
            logger.error(f"❌ Error fetching stock list: {e}")
            return self._stock_list_cache or []
    
    def get_real_time_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get real-time stock price (always fresh)"""
        cache_key = f"price:{symbol}"
        strategy = LOAD_STRATEGIES[DataType.REAL_TIME_PRICE.value]
        
        # Check cache (very short TTL for real-time data)
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for real-time price: {symbol}")
            return cached
        
        try:
            logger.debug(f"💹 Fetching real-time price for: {symbol}")
            price_data = self.client.get_real_time_quote(symbol)
            
            if price_data:
                # Cache for very short time
                self.cache.set(cache_key, price_data, ttl=strategy.cache_ttl)
                return price_data
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error fetching real-time price for {symbol}: {e}")
            return None
    
    def get_historical_prices(self, symbol: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """Get historical price data"""
        cache_key = f"historical:{symbol}:{start_date}:{end_date}"
        strategy = LOAD_STRATEGIES[DataType.HISTORICAL_PRICES]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"🎯 Cache hit for historical prices: {symbol}")
            return cached
        
        try:
            logger.info(f"📈 Fetching historical prices for: {symbol}")
            
            # Use the full historical price endpoint
            endpoint = "/historical-price-eod/full"
            params = {"symbol": symbol}
            
            if start_date:
                params["from"] = start_date
            if end_date:
                params["to"] = end_date
            
            data = self.client._make_request(endpoint, params)
            
            # Convert to DataFrame
            if data and "historical" in data:
                df = pd.DataFrame(data["historical"])
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')
                
                # Cache the result
                self.cache.set(cache_key, df, ttl=strategy.cache_ttl)
                
                logger.info(f"✅ Loaded {len(df)} historical prices for {symbol}")
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"❌ Error fetching historical prices for {symbol}: {e}")
            return pd.DataFrame()
    
    def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Get detailed company profile (on-demand)"""
        cache_key = f"profile:{symbol}"
        strategy = LOAD_STRATEGIES[DataType.COMPANY_PROFILE]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for company profile: {symbol}")
            return cached
        
        try:
            logger.info(f"🏢 Fetching company profile for: {symbol}")
            profile_data = self.client.fetch_symbol_details(symbol)
            
            if profile_data:
                # Cache the result
                self.cache.set(cache_key, profile_data, ttl=strategy.cache_ttl)
                return profile_data
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error fetching company profile for {symbol}: {e}")
            return {}
    
    def get_income_statement(self, symbol: str, period: str = None) -> Dict[str, Any]:
        """Get income statement data (on-demand)"""
        cache_key = f"income:{symbol}:{period or 'latest'}"
        strategy = LOAD_STRATEGIES[DataType.INCOME_STATEMENT]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for income statement: {symbol}")
            return cached
        
        try:
            logger.info(f"📊 Fetching income statement for: {symbol}")
            endpoint = "/income-statement"
            params = {"symbol": symbol}
            if period:
                params["period"] = period  # Only add period if provided
            
            data = self.client._make_request(endpoint, params)
            
            # Process and cache the result
            result = {
                "symbol": symbol,
                "period": period or "latest",
                "data": data if isinstance(data, list) else [],
                "fetched_at": datetime.now().isoformat()
            }
            
            self.cache.set(cache_key, result, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded income statement for {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error fetching income statement for {symbol}: {e}")
    def get_financials(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive financial data (on-demand)"""
        cache_key = f"financials:{symbol}"
        strategy = LOAD_STRATEGIES[DataType.FINANCIALS.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for financials: {symbol}")
            return cached
        
        try:
            logger.info(f"💰 Fetching comprehensive financials for: {symbol}")
            financials = self.client.get_comprehensive_financial_data(symbol)
            
            if financials:
                # Cache the result
                self.cache.set(cache_key, financials, ttl=strategy.cache_ttl)
                return financials
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error fetching financials for {symbol}: {e}")
            return {}
    
    # === NEW COMPREHENSIVE METHODS ===
    
    def get_balance_sheet(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get balance sheet data (on-demand)"""
        cache_key = f"balance_sheet:{symbol}:{period}"
        strategy = LOAD_STRATEGIES[DataType.BALANCE_SHEET.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for balance sheet: {symbol}")
            return cached
        
        try:
            logger.info(f"📊 Fetching balance sheet for: {symbol}")
            balance_sheet = self.client.get_balance_sheet_statement(symbol, period)
            
            # Cache the result
            self.cache.set(cache_key, balance_sheet, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded balance sheet for {symbol}")
            return balance_sheet
            
        except Exception as e:
            logger.error(f"❌ Error fetching balance sheet for {symbol}: {e}")
            return []
    
    def get_cash_flow(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get cash flow data (on-demand)"""
        cache_key = f"cash_flow:{symbol}:{period}"
        strategy = LOAD_STRATEGIES[DataType.CASH_FLOW.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for cash flow: {symbol}")
            return cached
        
        try:
            logger.info(f"💵 Fetching cash flow for: {symbol}")
            cash_flow = self.client.get_cash_flow_statement(symbol, period)
            
            # Cache the result
            self.cache.set(cache_key, cash_flow, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded cash flow for {symbol}")
            return cash_flow
            
        except Exception as e:
            logger.error(f"❌ Error fetching cash flow for {symbol}: {e}")
            return []
    
    def get_key_metrics(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get key financial metrics (on-demand)"""
        cache_key = f"key_metrics:{symbol}:{period}"
        strategy = LOAD_STRATEGIES[DataType.KEY_METRICS.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for key metrics: {symbol}")
            return cached
        
        try:
            logger.info(f"📈 Fetching key metrics for: {symbol}")
            metrics = self.client.get_key_metrics(symbol, period)
            
            # Cache the result
            self.cache.set(cache_key, metrics, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded key metrics for {symbol}")
            return metrics
            
        except Exception as e:
            logger.error(f"❌ Error fetching key metrics for {symbol}: {e}")
            return []
    
    def get_financial_ratios(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Get financial ratios (on-demand)"""
        cache_key = f"financial_ratios:{symbol}:{period}"
        strategy = LOAD_STRATEGIES[DataType.FINANCIAL_RATIOS.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for financial ratios: {symbol}")
            return cached
        
        try:
            logger.info(f"� Fetching financial ratios for: {symbol}")
            ratios = self.client.get_financial_ratios(symbol, period)
            
            # Cache the result
            self.cache.set(cache_key, ratios, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded financial ratios for {symbol}")
            return ratios
            
        except Exception as e:
            logger.error(f"❌ Error fetching financial ratios for {symbol}: {e}")
            return []
    
    def get_financial_scores(self, symbol: str) -> List[Dict[str, Any]]:
        """Get financial health scores (on-demand)"""
        cache_key = f"financial_scores:{symbol}"
        strategy = LOAD_STRATEGIES[DataType.FINANCIAL_SCORES.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for financial scores: {symbol}")
            return cached
        
        try:
            logger.info(f"🎯 Fetching financial scores for: {symbol}")
            scores = self.client.get_financial_scores(symbol)
            
            # Cache the result
            self.cache.set(cache_key, scores, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded financial scores for {symbol}")
            return scores
            
        except Exception as e:
            logger.error(f"❌ Error fetching financial scores for {symbol}: {e}")
            return []
    
    def get_analyst_ratings(self, symbol: str) -> List[Dict[str, Any]]:
        """Get analyst ratings (on-demand)"""
        cache_key = f"analyst_ratings:{symbol}"
        strategy = LOAD_STRATEGIES[DataType.ANALYST_RATINGS.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for analyst ratings: {symbol}")
            return cached
        
        try:
            logger.info(f"⭐ Fetching analyst ratings for: {symbol}")
            ratings = self.client.get_ratings_snapshot(symbol)
            
            # Cache the result
            self.cache.set(cache_key, ratings, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded analyst ratings for {symbol}")
            return ratings
            
        except Exception as e:
            logger.error(f"❌ Error fetching analyst ratings for {symbol}: {e}")
            return []
    
    def get_price_targets(self, symbol: str) -> List[Dict[str, Any]]:
        """Get price targets (on-demand)"""
        cache_key = f"price_targets:{symbol}"
        strategy = LOAD_STRATEGIES[DataType.PRICE_TARGETS.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for price targets: {symbol}")
            return cached
        
        try:
            logger.info(f"🎯 Fetching price targets for: {symbol}")
            targets = self.client.get_price_target_consensus(symbol)
            
            # Cache the result
            self.cache.set(cache_key, targets, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded price targets for {symbol}")
            return targets
            
        except Exception as e:
            logger.error(f"❌ Error fetching price targets for {symbol}: {e}")
            return []
    
    def get_stock_grades(self, symbol: str) -> List[Dict[str, Any]]:
        """Get stock grades (on-demand)"""
        cache_key = f"stock_grades:{symbol}"
        strategy = LOAD_STRATEGIES[DataType.STOCK_GRADES.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for stock grades: {symbol}")
            return cached
        
        try:
            logger.info(f"📊 Fetching stock grades for: {symbol}")
            grades = self.client.get_stock_grades(symbol)
            
            # Store in database
            if grades:
                try:
                    # Use proper repository pattern - follows Dependency Inversion Principle
                    from app.db_storage.repositories import get_database_service
                    db_service = get_database_service()
                    
                    if db_service.is_available():
                        success = db_service.stock_grades.store_grades(symbol, grades)
                        if success:
                            logger.info(f"✅ Stored {len(grades)} stock grades in database for {symbol}")
                    else:
                        logger.warning("⚠️  Database service not available - skipping storage")
                        
                except Exception as db_error:
                    logger.warning(f"⚠️  Could not store stock grades in database: {db_error}")
            
            # Cache the result
            self.cache.set(cache_key, grades, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded stock grades for {symbol}")
            return grades
            
        except Exception as e:
            logger.error(f"❌ Error fetching stock grades for {symbol}: {e}")
            return []
    
    def get_market_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get market news (on-demand)"""
        cache_key = f"market_news:{limit}"
        strategy = LOAD_STRATEGIES[DataType.MARKET_NEWS.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for market news")
            return cached
        
        try:
            logger.info(f"📰 Fetching market news")
            news_summary = self.client.get_market_news_summary(limit=limit)
            
            # Combine all news types
            all_news = []
            for news_type, articles in news_summary.items():
                if isinstance(articles, list):
                    all_news.extend(articles[:limit//6])  # Distribute limit across types
            
            # Cache the result
            self.cache.set(cache_key, all_news, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded {len(all_news)} market news articles")
            return all_news
            
        except Exception as e:
            logger.error(f"❌ Error fetching market news: {e}")
            return []
    
    def get_earnings_transcript(self, symbol: str, year: int = None, quarter: int = None) -> List[Dict[str, Any]]:
        """Get earnings transcript (on-demand, current year only)"""
        from datetime import datetime
        current_year = datetime.now().year
        
        # Default to current year if not specified
        if year is None:
            year = current_year
        
        cache_key = f"earnings_transcript:{symbol}:{year}:{quarter or 'all'}"
        strategy = LOAD_STRATEGIES[DataType.EARNINGS_TRANSCRIPTS.value]
        
        # Check cache
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"🎯 Cache hit for earnings transcript: {symbol} {year} Q{quarter}")
            return cached
        
        try:
            logger.info(f"📞 Fetching earnings transcript for: {symbol} {year} Q{quarter}")
            transcript = self.client.get_earning_transcript(symbol, year, quarter)
            
            # Cache the result
            self.cache.set(cache_key, transcript, ttl=strategy.cache_ttl)
            
            logger.info(f"✅ Loaded earnings transcript for {symbol} {year} Q{quarter}")
            return transcript
            
        except Exception as e:
            logger.error(f"❌ Error fetching earnings transcript for {symbol} {year} Q{quarter}: {e}")
            return []
    
    # === BULK OPERATIONS ===
    
    def load_all_data_for_symbols(self, symbols: List[str], load_on_demand: bool = False) -> Dict[str, Any]:
        """
        Load all data for multiple symbols with optimized strategy
        - Always loads real-time prices
        - Optionally loads on-demand data (profiles, financials, etc.)
        """
        logger.info(f"🚀 Starting optimized data load for {len(symbols)} symbols")
        
        results = {
            "symbols": symbols,
            "real_time_prices": {},
            "historical_prices": {},
            "company_profiles": {},
            "financials": {},
            "income_statements": {},
            "balance_sheets": {},
            "cash_flows": {},
            "key_metrics": {},
            "financial_ratios": {},
            "financial_scores": {},
            "analyst_ratings": {},
            "price_targets": {},
            "stock_grades": {},
            "market_news": {},
            "earnings_transcripts": {},
            "errors": [],
            "stats": {
                "total_symbols": len(symbols),
                "successful_prices": 0,
                "successful_profiles": 0,
                "successful_financials": 0,
                "successful_analyst_data": 0,
                "api_calls_saved": 0
            }
        }
        
        # Always load real-time prices (highest priority)
        logger.info("💹 Loading real-time prices...")
        for symbol in symbols:
            try:
                price_data = self.get_real_time_price(symbol)
                if price_data:
                    results["real_time_prices"][symbol] = price_data
                    results["stats"]["successful_prices"] += 1
                else:
                    results["errors"].append(f"No price data for {symbol}")
            except Exception as e:
                results["errors"].append(f"Price error for {symbol}: {str(e)}")
        
        # Load historical prices (medium priority)
        logger.info("📈 Loading historical prices...")
        for symbol in symbols:
            try:
                hist_data = self.get_historical_prices(symbol)
                if not hist_data.empty:
                    results["historical_prices"][symbol] = hist_data
            except Exception as e:
                results["errors"].append(f"Historical price error for {symbol}: {str(e)}")
        
        # Load on-demand data if requested
        if load_on_demand:
            logger.info("🏢 Loading company profiles...")
            for symbol in symbols:
                try:
                    profile = self.get_company_profile(symbol)
                    if profile:
                        results["company_profiles"][symbol] = profile
                        results["stats"]["successful_profiles"] += 1
                except Exception as e:
                    results["errors"].append(f"Profile error for {symbol}: {str(e)}")
            
            logger.info("💰 Loading comprehensive financials...")
            for symbol in symbols:
                try:
                    financials = self.get_financials(symbol)
                    if financials:
                        results["financials"][symbol] = financials
                        results["stats"]["successful_financials"] += 1
                except Exception as e:
                    results["errors"].append(f"Financials error for {symbol}: {str(e)}")
            
            logger.info("📊 Loading income statements...")
            for symbol in symbols:
                try:
                    income_stmt = self.get_income_statement(symbol)
                    if income_stmt:
                        results["income_statements"][symbol] = income_stmt
                except Exception as e:
                    results["errors"].append(f"Income statement error for {symbol}: {str(e)}")
            
            logger.info("📋 Loading balance sheets...")
            for symbol in symbols:
                try:
                    balance_sheet = self.get_balance_sheet(symbol)
                    if balance_sheet:
                        results["balance_sheets"][symbol] = balance_sheet
                except Exception as e:
                    results["errors"].append(f"Balance sheet error for {symbol}: {str(e)}")
            
            logger.info("💵 Loading cash flows...")
            for symbol in symbols:
                try:
                    cash_flow = self.get_cash_flow(symbol)
                    if cash_flow:
                        results["cash_flows"][symbol] = cash_flow
                except Exception as e:
                    results["errors"].append(f"Cash flow error for {symbol}: {str(e)}")
            
            logger.info("📈 Loading key metrics...")
            for symbol in symbols:
                try:
                    metrics = self.get_key_metrics(symbol)
                    if metrics:
                        results["key_metrics"][symbol] = metrics
                except Exception as e:
                    results["errors"].append(f"Key metrics error for {symbol}: {str(e)}")
            
            logger.info("📊 Loading financial ratios...")
            for symbol in symbols:
                try:
                    ratios = self.get_financial_ratios(symbol)
                    if ratios:
                        results["financial_ratios"][symbol] = ratios
                except Exception as e:
                    results["errors"].append(f"Financial ratios error for {symbol}: {str(e)}")
            
            logger.info("🎯 Loading financial scores...")
            for symbol in symbols:
                try:
                    scores = self.get_financial_scores(symbol)
                    if scores:
                        results["financial_scores"][symbol] = scores
                except Exception as e:
                    results["errors"].append(f"Financial scores error for {symbol}: {str(e)}")
            
            logger.info("⭐ Loading analyst ratings...")
            for symbol in symbols:
                try:
                    ratings = self.get_analyst_ratings(symbol)
                    if ratings:
                        results["analyst_ratings"][symbol] = ratings
                        results["stats"]["successful_analyst_data"] += 1
                except Exception as e:
                    results["errors"].append(f"Analyst ratings error for {symbol}: {str(e)}")
            
            logger.info("🎯 Loading price targets...")
            for symbol in symbols:
                try:
                    targets = self.get_price_targets(symbol)
                    if targets:
                        results["price_targets"][symbol] = targets
                        results["stats"]["successful_analyst_data"] += 1
                except Exception as e:
                    results["errors"].append(f"Price targets error for {symbol}: {str(e)}")
            
            logger.info("📊 Loading stock grades...")
            for symbol in symbols:
                try:
                    grades = self.get_stock_grades(symbol)
                    if grades:
                        results["stock_grades"][symbol] = grades
                        results["stats"]["successful_analyst_data"] += 1
                except Exception as e:
                    results["errors"].append(f"Stock grades error for {symbol}: {str(e)}")
            
            # Load market news (once for all symbols)
            logger.info("📰 Loading market news...")
            try:
                news = self.get_market_news(limit=20)
                if news:
                    results["market_news"] = news
            except Exception as e:
                results["errors"].append(f"Market news error: {str(e)}")
        
        # Log summary
        stats = results["stats"]
        logger.info(f"""
🎉 DATA LOAD SUMMARY:
   • Total Symbols: {stats['total_symbols']}
   • Real-time Prices: {stats['successful_prices']}/{stats['total_symbols']}
   • Company Profiles: {stats['successful_profiles']}/{stats['total_symbols']}
   • Financials: {stats['successful_financials']}/{stats['total_symbols']}
   • Analyst Data: {stats['successful_analyst_data']}/{stats['total_symbols']}
   • Errors: {len(results['errors'])}
        """.strip())
        
        return results
    
    def preload_essential_data(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Preload only essential data (real-time prices + historical prices)
        Other data will be loaded on-demand when requested
        """
        return self.load_all_data_for_symbols(symbols, load_on_demand=False)
    
    def get_on_demand_data(self, symbol: str, data_types: List[str] = None) -> Dict[str, Any]:
        """
        Get specific data types on-demand for a single symbol
        Used when detailed information is needed for analysis
        """
        if data_types is None:
            data_types = ["profile", "financials", "income_statement", "balance_sheet", "cash_flow"]
        
        logger.info(f"🔍 Loading on-demand data for {symbol}: {data_types}")
        
        result = {"symbol": symbol, "data": {}, "errors": []}
        
        for data_type in data_types:
            try:
                if data_type == "profile":
                    result["data"]["profile"] = self.get_company_profile(symbol)
                elif data_type == "financials":
                    result["data"]["financials"] = self.get_financials(symbol)
                elif data_type == "income_statement":
                    result["data"]["income_statement"] = self.get_income_statement(symbol)
                elif data_type == "balance_sheet":
                    result["data"]["balance_sheet"] = self.get_balance_sheet(symbol)
                elif data_type == "cash_flow":
                    result["data"]["cash_flow"] = self.get_cash_flow(symbol)
                elif data_type == "key_metrics":
                    result["data"]["key_metrics"] = self.get_key_metrics(symbol)
                elif data_type == "financial_ratios":
                    result["data"]["financial_ratios"] = self.get_financial_ratios(symbol)
                elif data_type == "financial_scores":
                    result["data"]["financial_scores"] = self.get_financial_scores(symbol)
                elif data_type == "analyst_ratings":
                    result["data"]["analyst_ratings"] = self.get_analyst_ratings(symbol)
                elif data_type == "price_targets":
                    result["data"]["price_targets"] = self.get_price_targets(symbol)
                elif data_type == "stock_grades":
                    result["data"]["stock_grades"] = self.get_stock_grades(symbol)
                elif data_type == "market_news":
                    result["data"]["market_news"] = self.get_market_news()
                elif data_type == "earnings_transcript":
                    # For transcripts, we need year and quarter
                    current_year = datetime.now().year
                    result["data"]["earnings_transcript"] = self.get_earnings_transcript(symbol, current_year, 1)
                else:
                    result["errors"].append(f"Unknown data type: {data_type}")
            except Exception as e:
                result["errors"].append(f"Error loading {data_type}: {str(e)}")
        
        return result
    
    # === CACHE MANAGEMENT ===
    
    def clear_cache(self, pattern: str = None):
        """Clear cache with optional pattern"""
        if pattern:
            self.cache.clear_pattern(pattern)
            logger.info(f"🧹 Cleared cache matching pattern: {pattern}")
        else:
            self.cache.clear_all()
            logger.info("🧹 Cleared all FMP cache")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "cache_size": self.cache.size(),
            "cache_keys": list(self.cache.keys()),
            "stock_list_cached": self._stock_list_cache is not None,
            "stock_list_age": (datetime.now() - self._stock_list_cache_time).seconds if self._stock_list_cache_time else None
        }


# Global instance for easy access
optimized_fmp_loader = OptimizedFMPLoader()
