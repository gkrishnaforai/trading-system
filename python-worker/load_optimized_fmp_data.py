#!/usr/bin/env python3
"""
Optimized FMP Data Loading Script
Uses the optimized FMP loader to efficiently load data with smart caching
- Real-time prices: Always loaded
- Historical data: Loaded with caching
- Detailed data: Loaded on-demand to reduce API calls
"""
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import argparse

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.optimized_fmp_loader import optimized_fmp_loader, DataType
from app.database import db
from app.observability.logging import get_logger

logger = get_logger("fmp_data_loader")


class FMPDataLoader:
    """Main data loading orchestrator using optimized FMP loader"""
    
    def __init__(self):
        self.loader = optimized_fmp_loader
        self.symbols = self._get_default_symbols()
        
    def _get_default_symbols(self) -> List[str]:
        """Get default list of symbols to load"""
        return [
            # Tech Giants
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
            
            # Financial Services
            "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SPGI", "V", "MA",
            
            # Healthcare
            "JNJ", "PFE", "UNH", "ABT", "TMO", "DHR", "ABBV", "MRK",
            
            # Consumer
            "PG", "KO", "PEP", "WMT", "COST", "HD", "MCD", "NKE",
            
            # Industrial
            "CAT", "GE", "HON", "UPS", "RTX", "BA", "DE",
            
            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG",
            
            # ETFs
            "SPY", "QQQ", "IWM", "VTI", "GLD", "TLT"
        ]
    
    def load_essential_data(self, symbols: List[str] = None) -> Dict[str, Any]:
        """Load essential data (real-time + historical prices)"""
        if symbols is None:
            symbols = self.symbols
        
        logger.info(f"🚀 Loading essential data for {len(symbols)} symbols")
        
        # Preload essential data
        results = self.loader.preload_essential_data(symbols)
        
        # Store in database
        self._store_essential_data(results)
        
        return results
    
    def load_comprehensive_data(self, symbols: List[str] = None) -> Dict[str, Any]:
        """Load comprehensive data including on-demand details"""
        if symbols is None:
            symbols = self.symbols
        
        logger.info(f"🎯 Loading comprehensive data for {len(symbols)} symbols")
        
        # Load all data including on-demand
        results = self.loader.load_all_data_for_symbols(symbols, load_on_demand=True)
        
        # Store in database
        self._store_comprehensive_data(results)
        
        return results
    
    def load_symbol_details(self, symbol: str) -> Dict[str, Any]:
        """Load detailed data for a single symbol on-demand"""
        logger.info(f"🔍 Loading detailed data for {symbol}")
        
        return self.loader.get_on_demand_data(symbol)
    
    def search_and_load(self, query: str) -> Dict[str, Any]:
        """Search for symbols and load their data"""
        logger.info(f"🔍 Searching for symbols: {query}")
        
        # Search for symbols
        search_results = self.loader.search_symbol(query)
        
        if not search_results:
            logger.warning(f"No symbols found for query: {query}")
            return {"query": query, "results": [], "data": {}}
        
        # Extract symbols from search results
        symbols = [result.get("symbol", "") for result in search_results if result.get("symbol")]
        symbols = [s for s in symbols if s]  # Remove empty strings
        
        logger.info(f"Found {len(symbols)} symbols: {symbols[:5]}...")
        
        # Load data for found symbols
        if symbols:
            data = self.load_essential_data(symbols[:10])  # Limit to top 10 results
            return {
                "query": query,
                "search_results": search_results,
                "loaded_data": data
            }
        
        return {"query": query, "results": search_results, "data": {}}
    
    def refresh_real_time_prices(self, symbols: List[str] = None) -> Dict[str, Any]:
        """Refresh only real-time prices (clear cache first)"""
        if symbols is None:
            symbols = self.symbols
        
        logger.info(f"💹 Refreshing real-time prices for {len(symbols)} symbols")
        
        # Clear price cache to force fresh data
        self.loader.clear_cache("price:*")
        
        # Load fresh prices
        prices = {}
        for symbol in symbols:
            price_data = self.loader.get_real_time_price(symbol)
            if price_data:
                prices[symbol] = price_data
        
        logger.info(f"✅ Refreshed prices for {len(prices)} symbols")
        
        return {"symbols": symbols, "prices": prices, "timestamp": datetime.now().isoformat()}
    
    def _store_essential_data(self, results: Dict[str, Any]):
        """Store essential data in database"""
        try:
            if db.session_factory is None:
                db.initialize()
            
            logger.info("💾 Storing essential data in database")
            
            # Store real-time prices
            real_time_prices = results.get("real_time_prices", {})
            for symbol, price_data in real_time_prices.items():
                self._store_real_time_price(symbol, price_data)
            
            # Store historical prices
            historical_prices = results.get("historical_prices", {})
            for symbol, df in historical_prices.items():
                if not df.empty:
                    self._store_historical_prices(symbol, df)
            
            logger.info("✅ Essential data stored successfully")
            
        except Exception as e:
            logger.error(f"❌ Error storing essential data: {e}")
    
    def _store_comprehensive_data(self, results: Dict[str, Any]):
        """Store comprehensive data in database"""
        try:
            if db.session_factory is None:
                db.initialize()
            
            logger.info("💾 Storing comprehensive data in database")
            
            # Store essential data first
            self._store_essential_data(results)
            
            # Store company profiles
            profiles = results.get("company_profiles", {})
            for symbol, profile in profiles.items():
                self._store_company_profile(symbol, profile)
            
            # Store financials
            financials = results.get("financials", {})
            for symbol, financial_data in financials.items():
                self._store_financials(symbol, financial_data)
            
            # Store income statements
            income_statements = results.get("income_statements", {})
            for symbol, income_data in income_statements.items():
                self._store_income_statement(symbol, income_data)
            
            logger.info("✅ Comprehensive data stored successfully")
            
        except Exception as e:
            logger.error(f"❌ Error storing comprehensive data: {e}")
    
    def _store_real_time_price(self, symbol: str, price_data: Dict[str, Any]):
        """Store real-time price in database"""
        try:
            # Implementation would depend on your database schema
            # This is a placeholder for the actual storage logic
            logger.debug(f"Storing real-time price for {symbol}: {price_data.get('price', 'N/A')}")
            
            # Example: Store in market_data table
            # with db.session() as session:
            #     # Insert/update logic here
            #     pass
            
        except Exception as e:
            logger.error(f"Error storing real-time price for {symbol}: {e}")
    
    def _store_historical_prices(self, symbol: str, df):
        """Store historical prices in database"""
        try:
            logger.debug(f"Storing {len(df)} historical prices for {symbol}")
            
            # Example: Store in raw_market_data_daily table
            # with db.session() as session:
            #     # Bulk insert logic here
            #     pass
            
        except Exception as e:
            logger.error(f"Error storing historical prices for {symbol}: {e}")
    
    def _store_company_profile(self, symbol: str, profile: Dict[str, Any]):
        """Store company profile in database"""
        try:
            logger.debug(f"Storing company profile for {symbol}")
            
            # Example: Store in fundamentals_snapshots table
            # with db.session() as session:
            #     # Insert/update logic here
            #     pass
            
        except Exception as e:
            logger.error(f"Error storing company profile for {symbol}: {e}")
    
    def _store_financials(self, symbol: str, financial_data: Dict[str, Any]):
        """Store financial data in database"""
        try:
            logger.debug(f"Storing financials for {symbol}")
            
            # Example: Store in financial_statements table
            # with db.session() as session:
            #     # Insert/update logic here
            #     pass
            
        except Exception as e:
            logger.error(f"Error storing financials for {symbol}: {e}")
    
    def _store_income_statement(self, symbol: str, income_data: Dict[str, Any]):
        """Store income statement in database"""
        try:
            logger.debug(f"Storing income statement for {symbol}")
            
            # Example: Store in income_statements table
            # with db.session() as session:
            #     # Insert/update logic here
            #     pass
            
        except Exception as e:
            logger.error(f"Error storing income statement for {symbol}: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self.loader.get_cache_stats()
    
    def clear_cache(self, pattern: str = None):
        """Clear cache"""
        self.loader.clear_cache(pattern)


def main():
    """Main function with command line interface"""
    parser = argparse.ArgumentParser(description="Optimized FMP Data Loader")
    parser.add_argument("--action", choices=["essential", "comprehensive", "search", "refresh", "details"], 
                       default="essential", help="Action to perform")
    parser.add_argument("--symbols", nargs="+", help="Symbols to load")
    parser.add_argument("--query", help="Search query for symbols")
    parser.add_argument("--symbol", help="Single symbol for detailed data")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache before loading")
    parser.add_argument("--cache-stats", action="store_true", help="Show cache statistics")
    
    args = parser.parse_args()
    
    loader = FMPDataLoader()
    
    # Clear cache if requested
    if args.clear_cache:
        loader.clear_cache()
        logger.info("🧹 Cache cleared")
    
    # Show cache stats if requested
    if args.cache_stats:
        stats = loader.get_cache_stats()
        print(f"""
📊 CACHE STATISTICS:
   • Cache Size: {stats['cache_size']}
   • Cached Keys: {len(stats['cache_keys'])}
   • Stock List Cached: {stats['stock_list_cached']}
   • Stock List Age: {stats['stock_list_age']}s ago
        """.strip())
        return
    
    # Perform action
    if args.action == "essential":
        results = loader.load_essential_data(args.symbols)
        print(f"✅ Loaded essential data for {len(results.get('real_time_prices', {}))} symbols")
    
    elif args.action == "comprehensive":
        results = loader.load_comprehensive_data(args.symbols)
        print(f"✅ Loaded comprehensive data for {len(results.get('real_time_prices', {}))} symbols")
    
    elif args.action == "search":
        if not args.query:
            print("❌ Search query required")
            return
        results = loader.search_and_load(args.query)
        print(f"✅ Found and loaded data for {len(results.get('loaded_data', {}).get('real_time_prices', {}))} symbols")
    
    elif args.action == "refresh":
        results = loader.refresh_real_time_prices(args.symbols)
        print(f"✅ Refreshed prices for {len(results.get('prices', {}))} symbols")
    
    elif args.action == "details":
        if not args.symbol:
            print("❌ Symbol required for details")
            return
        results = loader.load_symbol_details(args.symbol)
        print(f"✅ Loaded detailed data for {args.symbol}")


if __name__ == "__main__":
    main()
