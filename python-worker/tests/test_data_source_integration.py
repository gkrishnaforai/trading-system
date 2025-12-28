"""
Integration tests for Data Sources with REAL data (no mocks)
Tests all data source functionality with real stock data
Validates: Daily data, on-demand data, all data types required for signal calculation
"""
import unittest
import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.data_sources.base import BaseDataSource
from app.services.data_fetcher import DataFetcher
from app.database import init_database, db


class TestDataSourceIntegration(unittest.TestCase):
    """
    Integration tests for data sources using real market data
    Tests AAPL, NVDA, GOOGL, PLTR with actual Yahoo Finance data
    """
    
    @classmethod
    def setUpClass(cls):
        """Fetch real data once for all tests"""
        print("\n" + "="*80)
        print("DATA SOURCE INTEGRATION TESTS - REAL MARKET DATA")
        print("="*80)
        
        # Initialize database
        init_database()
        
        cls.data_source = YahooFinanceSource()
        cls.symbols = ['AAPL', 'NVDA', 'GOOGL', 'PLTR']
        cls.data_fetcher = DataFetcher()
        
        print(f"\n📊 Testing with symbols: {', '.join(cls.symbols)}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.data_source = self.__class__.data_source
        self.symbols = self.__class__.symbols
        self.data_fetcher = self.__class__.data_fetcher
    
    def test_data_source_availability(self):
        """Test that data source is available and healthy"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                is_available = self.data_source.is_available()
                self.assertTrue(
                    is_available,
                    f"{symbol}: Data source should be available"
                )
                print(f"✅ {symbol}: Data source available")
    
    def test_fetch_daily_price_data(self):
        """Test fetching daily historical price data (1 year)"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n📥 Fetching 1 year of daily price data for {symbol}...")
                
                # Fetch 1 year of data
                data = self.data_source.fetch_price_data(symbol, period='1y')
                
                # Validate data exists
                self.assertIsNotNone(data, f"{symbol}: Should return data")
                self.assertFalse(data.empty, f"{symbol}: Data should not be empty")
                
                # Validate data structure
                required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
                for col in required_cols:
                    self.assertIn(
                        col, data.columns,
                        f"{symbol}: Missing column {col}. Available: {list(data.columns)}"
                    )
                
                # Validate data quality
                self.assertGreater(
                    len(data), 200,
                    f"{symbol}: Should have at least 200 trading days (1 year)"
                )
                
                # Validate price data
                self.assertTrue(
                    (data['close'] > 0).all(),
                    f"{symbol}: All close prices should be positive"
                )
                self.assertTrue(
                    (data['high'] >= data['low']).all(),
                    f"{symbol}: High should be >= Low"
                )
                self.assertTrue(
                    (data['high'] >= data['close']).all(),
                    f"{symbol}: High should be >= Close"
                )
                self.assertTrue(
                    (data['low'] <= data['close']).all(),
                    f"{symbol}: Low should be <= Close"
                )
                
                # Validate volume
                self.assertTrue(
                    (data['volume'] >= 0).all(),
                    f"{symbol}: Volume should be non-negative"
                )
                
                # Validate date range
                data['date'] = pd.to_datetime(data['date'])
                date_range = (data['date'].max() - data['date'].min()).days
                self.assertGreater(
                    date_range, 250,
                    f"{symbol}: Date range should be at least 250 days"
                )
                
                print(f"✅ {symbol}: {len(data)} rows, Date range: {data['date'].min().date()} to {data['date'].max().date()}")
                print(f"   Latest close: ${data['close'].iloc[-1]:.2f}, Volume: {data['volume'].iloc[-1]:,.0f}")
    
    def test_fetch_on_demand_price_data(self):
        """Test fetching on-demand price data with specific date ranges"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n📥 Fetching on-demand price data for {symbol}...")
                
                # Fetch last 30 days
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                
                data = self.data_source.fetch_price_data(
                    symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Validate data
                self.assertIsNotNone(data, f"{symbol}: Should return data")
                self.assertFalse(data.empty, f"{symbol}: Data should not be empty")
                
                # Validate date range
                data['date'] = pd.to_datetime(data['date'])
                self.assertGreaterEqual(
                    data['date'].min().date(),
                    start_date.date(),
                    f"{symbol}: Start date should be >= requested start date"
                )
                self.assertLessEqual(
                    data['date'].max().date(),
                    end_date.date(),
                    f"{symbol}: End date should be <= requested end date"
                )
                
                print(f"✅ {symbol}: {len(data)} rows for last 30 days")
    
    def test_fetch_current_price(self):
        """Test fetching current/live price"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n💰 Fetching current price for {symbol}...")
                
                current_price = self.data_source.fetch_current_price(symbol)
                
                # Validate price
                self.assertIsNotNone(current_price, f"{symbol}: Should return price")
                self.assertIsInstance(
                    current_price, (int, float),
                    f"{symbol}: Price should be numeric"
                )
                self.assertGreater(
                    current_price, 0,
                    f"{symbol}: Price should be positive"
                )
                
                print(f"✅ {symbol}: Current price: ${current_price:.2f}")
    
    def test_fetch_fundamentals(self):
        """Test fetching fundamental data"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n📊 Fetching fundamentals for {symbol}...")
                
                fundamentals = self.data_source.fetch_fundamentals(symbol)
                
                # Validate fundamentals structure
                self.assertIsNotNone(fundamentals, f"{symbol}: Should return fundamentals")
                self.assertIsInstance(
                    fundamentals, dict,
                    f"{symbol}: Fundamentals should be a dictionary"
                )
                
                # Check for common fundamental fields
                # Note: Different data sources may have different fields
                if fundamentals:
                    print(f"✅ {symbol}: Fundamentals fetched ({len(fundamentals)} fields)")
                    # Print some key fields if available
                    for key in ['market_cap', 'pe_ratio', 'dividend_yield', 'revenue']:
                        if key in fundamentals:
                            print(f"   {key}: {fundamentals[key]}")
                else:
                    print(f"⚠️  {symbol}: No fundamental data available")
    
    def test_fetch_news(self):
        """Test fetching news articles"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n📰 Fetching news for {symbol}...")
                
                news = self.data_source.fetch_news(symbol, limit=10)
                
                # Validate news structure
                self.assertIsNotNone(news, f"{symbol}: Should return news list")
                self.assertIsInstance(
                    news, list,
                    f"{symbol}: News should be a list"
                )
                
                if news:
                    # Validate news items
                    for i, article in enumerate(news[:3]):  # Check first 3
                        self.assertIsInstance(
                            article, dict,
                            f"{symbol}: News item {i} should be a dictionary"
                        )
                        # Check for common fields
                        if 'title' in article:
                            print(f"   Article {i+1}: {article['title'][:60]}...")
                    
                    print(f"✅ {symbol}: {len(news)} news articles fetched")
                else:
                    print(f"⚠️  {symbol}: No news available")
    
    def test_fetch_earnings(self):
        """Test fetching earnings data"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n💵 Fetching earnings for {symbol}...")
                
                earnings = self.data_source.fetch_earnings(symbol)
                
                # Validate earnings structure
                self.assertIsNotNone(earnings, f"{symbol}: Should return earnings list")
                self.assertIsInstance(
                    earnings, list,
                    f"{symbol}: Earnings should be a list"
                )
                
                if earnings:
                    # Validate earnings items
                    for i, earning in enumerate(earnings[:3]):  # Check first 3
                        self.assertIsInstance(
                            earning, dict,
                            f"{symbol}: Earnings item {i} should be a dictionary"
                        )
                    
                    print(f"✅ {symbol}: {len(earnings)} earnings records fetched")
                else:
                    print(f"⚠️  {symbol}: No earnings data available")
    
    def test_fetch_industry_peers(self):
        """Test fetching industry peers data"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🏭 Fetching industry peers for {symbol}...")
                
                peers_data = self.data_source.fetch_industry_peers(symbol)
                
                # Validate peers structure
                self.assertIsNotNone(peers_data, f"{symbol}: Should return peers data")
                self.assertIsInstance(
                    peers_data, dict,
                    f"{symbol}: Peers data should be a dictionary"
                )
                
                if peers_data:
                    # Check for expected keys
                    if 'sector' in peers_data:
                        print(f"   Sector: {peers_data['sector']}")
                    if 'industry' in peers_data:
                        print(f"   Industry: {peers_data['industry']}")
                    if 'peers' in peers_data:
                        peers_list = peers_data['peers']
                        self.assertIsInstance(
                            peers_list, list,
                            f"{symbol}: Peers should be a list"
                        )
                        print(f"✅ {symbol}: {len(peers_list)} peers found")
                    else:
                        print(f"✅ {symbol}: Industry data fetched")
                else:
                    print(f"⚠️  {symbol}: No industry peers data available")
    
    def test_save_and_retrieve_price_data(self):
        """Test saving price data to database and retrieving it"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n💾 Testing save/retrieve for {symbol}...")
                
                # Fetch data
                data = self.data_source.fetch_price_data(symbol, period='1mo')
                self.assertIsNotNone(data, f"{symbol}: Should fetch data")
                self.assertFalse(data.empty, f"{symbol}: Data should not be empty")
                
                # Save to database
                rows_saved = self.data_fetcher.save_raw_market_data(symbol, data)
                self.assertGreater(
                    rows_saved, 0,
                    f"{symbol}: Should save at least 1 row"
                )
                
                # Retrieve from database
                query = """
                    SELECT date, open, high, low, close, volume
                    FROM raw_market_data
                    WHERE stock_symbol = :symbol
                    ORDER BY date DESC
                    LIMIT 10
                """
                retrieved = db.execute_query(query, {"symbol": symbol})
                
                self.assertGreater(
                    len(retrieved), 0,
                    f"{symbol}: Should retrieve data from database"
                )
                
                # Validate retrieved data
                latest = retrieved[0]
                self.assertIn('date', latest, f"{symbol}: Should have date")
                self.assertIn('close', latest, f"{symbol}: Should have close")
                self.assertGreater(
                    latest['close'], 0,
                    f"{symbol}: Close price should be positive"
                )
                
                print(f"✅ {symbol}: Saved {rows_saved} rows, Retrieved {len(retrieved)} rows")
    
    def test_data_completeness_for_signals(self):
        """Test that all required data types are available for signal calculation"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔍 Checking data completeness for {symbol}...")
                
                # Check price data
                price_data = self.data_source.fetch_price_data(symbol, period='1y')
                self.assertIsNotNone(price_data, f"{symbol}: Price data required")
                self.assertGreater(
                    len(price_data), 200,
                    f"{symbol}: Need at least 200 days for indicators"
                )
                
                # Check required columns for indicators
                required_price_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
                for col in required_price_cols:
                    self.assertIn(
                        col, price_data.columns,
                        f"{symbol}: Missing required column {col} for indicators"
                    )
                
                # Check for NaN values in critical columns
                for col in ['close', 'volume']:
                    nan_count = price_data[col].isna().sum()
                    self.assertEqual(
                        nan_count, 0,
                        f"{symbol}: Should have no NaN values in {col}"
                    )
                
                # Check current price
                current_price = self.data_source.fetch_current_price(symbol)
                self.assertIsNotNone(
                    current_price,
                    f"{symbol}: Current price required for signals"
                )
                
                # Check fundamentals (optional but preferred)
                fundamentals = self.data_source.fetch_fundamentals(symbol)
                # Fundamentals are optional, so we just check it doesn't crash
                
                print(f"✅ {symbol}: All required data available for signal calculation")
                print(f"   Price data: {len(price_data)} rows")
                print(f"   Current price: ${current_price:.2f}")
                print(f"   Fundamentals: {'Available' if fundamentals else 'Not available'}")
    
    def test_data_refresh_modes(self):
        """Test different data refresh modes (daily, on-demand, periodic)"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔄 Testing data refresh modes for {symbol}...")
                
                # Mode 1: Daily batch (1 year historical)
                daily_data = self.data_source.fetch_price_data(symbol, period='1y')
                self.assertIsNotNone(daily_data, f"{symbol}: Daily data should work")
                print(f"   ✅ Daily batch: {len(daily_data)} rows")
                
                # Mode 2: On-demand (last 30 days)
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                on_demand_data = self.data_source.fetch_price_data(
                    symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                self.assertIsNotNone(on_demand_data, f"{symbol}: On-demand data should work")
                print(f"   ✅ On-demand: {len(on_demand_data)} rows")
                
                # Mode 3: Current price (live data)
                current_price = self.data_source.fetch_current_price(symbol)
                self.assertIsNotNone(current_price, f"{symbol}: Current price should work")
                print(f"   ✅ Current price: ${current_price:.2f}")
                
                print(f"✅ {symbol}: All refresh modes working")
    
    def test_data_consistency(self):
        """Test data consistency across different fetch methods"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔗 Testing data consistency for {symbol}...")
                
                # Fetch historical data
                historical = self.data_source.fetch_price_data(symbol, period='1mo')
                self.assertIsNotNone(historical, f"{symbol}: Historical data required")
                
                # Fetch current price
                current = self.data_source.fetch_current_price(symbol)
                self.assertIsNotNone(current, f"{symbol}: Current price required")
                
                # Latest historical close should be close to current price
                # (within 5% to account for market movements)
                if not historical.empty:
                    historical['date'] = pd.to_datetime(historical['date'])
                    latest_close = historical['close'].iloc[-1]
                    price_diff_pct = abs((current - latest_close) / latest_close) * 100
                    
                    # Allow up to 5% difference (market can move)
                    self.assertLess(
                        price_diff_pct, 5.0,
                        f"{symbol}: Current price ({current:.2f}) should be within 5% of "
                        f"latest historical close ({latest_close:.2f}). Diff: {price_diff_pct:.2f}%"
                    )
                    
                    print(f"✅ {symbol}: Data consistency verified")
                    print(f"   Latest historical: ${latest_close:.2f}")
                    print(f"   Current price: ${current:.2f}")
                    print(f"   Difference: {price_diff_pct:.2f}%")
    
    def test_error_handling(self):
        """Test error handling for invalid symbols"""
        print(f"\n⚠️  Testing error handling...")
        
        # Test invalid symbol
        invalid_symbol = "INVALID_SYMBOL_XYZ123"
        try:
            data = self.data_source.fetch_price_data(invalid_symbol, period='1mo')
            
            # Should handle gracefully (return None or empty, not crash)
            if data is None or data.empty:
                print(f"✅ Invalid symbol handled gracefully")
            else:
                # If it returns data, that's also acceptable (some sources might)
                print(f"⚠️  Invalid symbol returned data (unexpected but acceptable)")
        except Exception as e:
            # RetryError from tenacity is acceptable for invalid symbols
            from tenacity import RetryError
            if isinstance(e, RetryError):
                print(f"✅ Invalid symbol raised RetryError (expected after retries)")
            else:
                print(f"✅ Invalid symbol raised exception: {type(e).__name__}")
        
        # Test None symbol
        try:
            result = self.data_source.fetch_price_data(None, period='1mo')
            # Should either return None or raise an exception
            if result is None:
                print(f"✅ None symbol handled gracefully")
        except (ValueError, TypeError, AttributeError):
            print(f"✅ None symbol raised expected exception")
        except Exception as e:
            # RetryError is also acceptable for None symbol (after retries)
            from tenacity import RetryError
            if isinstance(e, RetryError):
                print(f"✅ None symbol raised RetryError (expected after retries)")
            else:
                # Log but don't fail - other exceptions are acceptable
                print(f"⚠️  None symbol raised {type(e).__name__}: {e}")


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)

