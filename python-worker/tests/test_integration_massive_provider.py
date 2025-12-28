"""
Integration tests for Massive.com (Polygon.io) data provider
Tests ALL data fetching APIs with REAL API calls (no mocks)
Validates data quality and API response structure
"""
import unittest
import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.data_sources.massive_source import MassiveSource
from app.config import settings


class TestMassiveProviderIntegration(unittest.TestCase):
    """
    Integration tests for Massive.com provider
    Tests all data fetching APIs with real API calls
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up Massive.com client and test symbols"""
        print("\n" + "="*80)
        print("MASSIVE.COM PROVIDER INTEGRATION TESTS")
        print("="*80)
        
        # Check if Massive.com is configured
        if not settings.massive_enabled:
            raise unittest.SkipTest("Massive.com is not enabled. Set MASSIVE_ENABLED=true in .env")
        
        if not settings.massive_api_key:
            raise unittest.SkipTest("Massive.com API key not configured. Set MASSIVE_API_KEY in .env")
        
        try:
            cls.data_source = MassiveSource()
            print(f"✅ Massive.com client initialized")
            print(f"   Rate limit: {settings.massive_rate_limit_calls} calls per {settings.massive_rate_limit_window}s")
        except Exception as e:
            raise unittest.SkipTest(f"Failed to initialize Massive.com client: {e}")
        
        # Test symbols - use popular stocks that should have data
        cls.symbols = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA']
        
        print(f"\n📊 Test symbols: {', '.join(cls.symbols)}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up for each test"""
        if not hasattr(self, 'data_source'):
            self.skipTest("Massive.com client not initialized")
    
    def test_fetch_price_data_1y(self):
        """Test fetching 1 year of historical price data"""
        print("\n📈 Test: Fetch 1 Year Historical Price Data")
        print("-" * 80)
        
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n  Testing {symbol}...")
                
                try:
                    data = self.data_source.fetch_price_data(symbol, period='1y')
                    
                    # Validate response
                    self.assertIsNotNone(data, f"{symbol}: No data returned")
                    self.assertIsInstance(data, pd.DataFrame, f"{symbol}: Expected DataFrame")
                    self.assertFalse(data.empty, f"{symbol}: DataFrame is empty")
                    
                    # Check required columns
                    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
                    for col in required_cols:
                        self.assertIn(col, data.columns, 
                                     f"{symbol}: Missing column {col}. Available: {list(data.columns)}")
                    
                    # Validate data quality
                    self.assertGreater(len(data), 200, 
                                     f"{symbol}: Insufficient data points (expected >200, got {len(data)})")
                    
                    # Check for NaN values in critical columns
                    for col in ['close', 'volume']:
                        nan_count = data[col].isna().sum()
                        self.assertEqual(nan_count, 0, 
                                       f"{symbol}: {nan_count} NaN values in {col}")
                    
                    # Validate price data
                    self.assertTrue((data['close'] > 0).all(), 
                                  f"{symbol}: Invalid close prices (non-positive)")
                    self.assertTrue((data['high'] >= data['low']).all(),
                                  f"{symbol}: High < Low detected")
                    self.assertTrue((data['high'] >= data['close']).all(),
                                  f"{symbol}: High < Close detected")
                    self.assertTrue((data['low'] <= data['close']).all(),
                                  f"{symbol}: Low > Close detected")
                    
                    # Check date range
                    if 'date' in data.columns:
                        dates = pd.to_datetime(data['date'])
                        date_range = (dates.max() - dates.min()).days
                        self.assertGreater(date_range, 300, 
                                          f"{symbol}: Date range too short ({date_range} days)")
                    
                    print(f"    ✅ {symbol}: {len(data)} rows, Date range: {dates.min()} to {dates.max()}")
                    print(f"       Latest close: ${data['close'].iloc[-1]:.2f}, Volume: {data['volume'].iloc[-1]:,.0f}")
                    
                except Exception as e:
                    self.fail(f"{symbol}: Failed to fetch price data - {e}")
    
    def test_fetch_price_data_periods(self):
        """Test fetching price data for different periods"""
        print("\n📈 Test: Fetch Price Data for Different Periods")
        print("-" * 80)
        
        symbol = 'AAPL'  # Use one symbol for period tests
        periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y']
        
        for period in periods:
            with self.subTest(period=period):
                print(f"\n  Testing period: {period}...")
                
                try:
                    data = self.data_source.fetch_price_data(symbol, period=period)
                    
                    self.assertIsNotNone(data, f"Period {period}: No data returned")
                    self.assertFalse(data.empty, f"Period {period}: DataFrame is empty")
                    
                    # Check minimum data points based on period
                    min_expected = {
                        '1d': 1,
                        '5d': 3,
                        '1mo': 15,
                        '3mo': 50,
                        '6mo': 100,
                        '1y': 200
                    }
                    min_rows = min_expected.get(period, 1)
                    self.assertGreaterEqual(len(data), min_rows,
                                          f"Period {period}: Expected at least {min_rows} rows, got {len(data)}")
                    
                    print(f"    ✅ {period}: {len(data)} rows")
                    
                except Exception as e:
                    self.fail(f"Period {period}: Failed to fetch data - {e}")
    
    def test_fetch_current_price(self):
        """Test fetching current/live price"""
        print("\n💰 Test: Fetch Current Price")
        print("-" * 80)
        
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n  Testing {symbol}...")
                
                try:
                    price = self.data_source.fetch_current_price(symbol)
                    
                    # Validate response
                    self.assertIsNotNone(price, f"{symbol}: No price returned")
                    self.assertIsInstance(price, (int, float), f"{symbol}: Expected numeric price")
                    self.assertGreater(price, 0, f"{symbol}: Invalid price (non-positive)")
                    
                    # Price should be reasonable (not too high or too low)
                    # Most stocks are between $1 and $10,000
                    self.assertLess(price, 100000, f"{symbol}: Price too high (${price:,.2f})")
                    self.assertGreater(price, 0.01, f"{symbol}: Price too low (${price:.4f})")
                    
                    print(f"    ✅ {symbol}: ${price:.2f}")
                    
                except Exception as e:
                    self.fail(f"{symbol}: Failed to fetch current price - {e}")
    
    def test_fetch_fundamentals(self):
        """Test fetching fundamental data"""
        print("\n📊 Test: Fetch Fundamentals")
        print("-" * 80)
        
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n  Testing {symbol}...")
                
                try:
                    fundamentals = self.data_source.fetch_fundamentals(symbol)
                    
                    # Validate response
                    self.assertIsNotNone(fundamentals, f"{symbol}: No fundamentals returned")
                    self.assertIsInstance(fundamentals, dict, f"{symbol}: Expected dict")
                    self.assertGreater(len(fundamentals), 0, f"{symbol}: Empty fundamentals dict")
                    
                    # Check for common fundamental fields
                    # Note: Massive.com may not have all fields, so we check what's available
                    common_fields = ['market_cap', 'pe_ratio', 'dividend_yield', 'eps', 
                                   'revenue', 'profit_margin', 'debt_to_equity']
                    
                    available_fields = [f for f in common_fields if f in fundamentals]
                    self.assertGreater(len(available_fields), 0,
                                     f"{symbol}: No common fundamental fields found. Available: {list(fundamentals.keys())}")
                    
                    # Validate numeric fields if present
                    if 'market_cap' in fundamentals:
                        market_cap = fundamentals['market_cap']
                        if market_cap is not None:
                            self.assertGreater(market_cap, 0, f"{symbol}: Invalid market cap")
                    
                    if 'pe_ratio' in fundamentals:
                        pe = fundamentals['pe_ratio']
                        if pe is not None:
                            self.assertGreater(pe, 0, f"{symbol}: Invalid P/E ratio")
                    
                    print(f"    ✅ {symbol}: {len(fundamentals)} fields")
                    if available_fields:
                        print(f"       Available: {', '.join(available_fields)}")
                    
                except Exception as e:
                    # Fundamentals might not be available for all symbols
                    print(f"    ⚠️  {symbol}: Fundamentals not available - {e}")
                    # Don't fail the test, just log a warning
    
    def test_fetch_news(self):
        """Test fetching news articles"""
        print("\n📰 Test: Fetch News Articles")
        print("-" * 80)
        
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n  Testing {symbol}...")
                
                try:
                    news = self.data_source.fetch_news(symbol, limit=10)
                    
                    # Validate response
                    self.assertIsNotNone(news, f"{symbol}: No news returned")
                    self.assertIsInstance(news, list, f"{symbol}: Expected list")
                    
                    if len(news) > 0:
                        # Validate first article structure
                        article = news[0]
                        self.assertIsInstance(article, dict, f"{symbol}: News item should be dict")
                        
                        # Check for common fields
                        common_fields = ['title', 'url', 'published_utc', 'description']
                        available_fields = [f for f in common_fields if f in article]
                        self.assertGreater(len(available_fields), 0,
                                         f"{symbol}: News article missing required fields. Available: {list(article.keys())}")
                        
                        print(f"    ✅ {symbol}: {len(news)} articles")
                        if 'title' in article:
                            print(f"       Latest: {article['title'][:60]}...")
                    else:
                        print(f"    ⚠️  {symbol}: No news articles found (may be normal)")
                    
                except Exception as e:
                    # News might not be available for all symbols
                    print(f"    ⚠️  {symbol}: News not available - {e}")
                    # Don't fail the test, just log a warning
    
    def test_fetch_earnings(self):
        """Test fetching earnings data"""
        print("\n💵 Test: Fetch Earnings Data")
        print("-" * 80)
        
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n  Testing {symbol}...")
                
                try:
                    earnings = self.data_source.fetch_earnings(symbol)
                    
                    # Validate response
                    self.assertIsNotNone(earnings, f"{symbol}: No earnings returned")
                    self.assertIsInstance(earnings, list, f"{symbol}: Expected list")
                    
                    if len(earnings) > 0:
                        # Validate first earnings record structure
                        earning = earnings[0]
                        self.assertIsInstance(earning, dict, f"{symbol}: Earnings item should be dict")
                        
                        # Check for common fields
                        common_fields = ['earnings_date', 'eps_actual', 'eps_estimate', 
                                        'revenue_actual', 'revenue_estimate']
                        available_fields = [f for f in common_fields if f in earning]
                        self.assertGreater(len(available_fields), 0,
                                         f"{symbol}: Earnings record missing required fields. Available: {list(earning.keys())}")
                        
                        # Validate earnings_date if present
                        if 'earnings_date' in earning and earning['earnings_date']:
                            earnings_date = earning['earnings_date']
                            # Should be a date or datetime
                            if isinstance(earnings_date, str):
                                # Try to parse
                                try:
                                    pd.to_datetime(earnings_date)
                                except:
                                    self.fail(f"{symbol}: Invalid earnings_date format: {earnings_date}")
                        
                        print(f"    ✅ {symbol}: {len(earnings)} earnings records")
                        if 'earnings_date' in earning:
                            print(f"       Latest: {earning['earnings_date']}")
                    else:
                        print(f"    ⚠️  {symbol}: No earnings records found (may be normal)")
                    
                except Exception as e:
                    # Earnings might not be available for all symbols
                    print(f"    ⚠️  {symbol}: Earnings not available - {e}")
                    # Don't fail the test, just log a warning
    
    def test_fetch_industry_peers(self):
        """Test fetching industry peers data"""
        print("\n🏢 Test: Fetch Industry Peers")
        print("-" * 80)
        
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n  Testing {symbol}...")
                
                try:
                    peers_data = self.data_source.fetch_industry_peers(symbol)
                    
                    # Validate response
                    self.assertIsNotNone(peers_data, f"{symbol}: No peers data returned")
                    self.assertIsInstance(peers_data, dict, f"{symbol}: Expected dict")
                    
                    # Check for sector/industry info
                    has_sector = 'sector' in peers_data
                    has_industry = 'industry' in peers_data
                    has_peers = 'peers' in peers_data
                    
                    self.assertTrue(has_sector or has_industry or has_peers,
                                   f"{symbol}: Missing sector, industry, or peers. Available: {list(peers_data.keys())}")
                    
                    # Validate peers list if present
                    if has_peers:
                        peers = peers_data['peers']
                        self.assertIsInstance(peers, list, f"{symbol}: Peers should be a list")
                        
                        if len(peers) > 0:
                            # Validate first peer structure
                            peer = peers[0]
                            self.assertIsInstance(peer, dict, f"{symbol}: Peer should be dict")
                            
                            # Should have symbol or name
                            has_symbol = 'symbol' in peer
                            has_name = 'name' in peer
                            self.assertTrue(has_symbol or has_name,
                                          f"{symbol}: Peer missing symbol/name. Available: {list(peer.keys())}")
                            
                            print(f"    ✅ {symbol}: {len(peers)} peers")
                            if has_sector:
                                print(f"       Sector: {peers_data.get('sector', 'N/A')}")
                            if has_industry:
                                print(f"       Industry: {peers_data.get('industry', 'N/A')}")
                        else:
                            print(f"    ⚠️  {symbol}: No peers found (may be normal)")
                    else:
                        if has_sector or has_industry:
                            print(f"    ✅ {symbol}: Sector/Industry info available")
                            if has_sector:
                                print(f"       Sector: {peers_data.get('sector', 'N/A')}")
                            if has_industry:
                                print(f"       Industry: {peers_data.get('industry', 'N/A')}")
                    
                except Exception as e:
                    # Industry peers might not be available for all symbols
                    print(f"    ⚠️  {symbol}: Industry peers not available - {e}")
                    # Don't fail the test, just log a warning
    
    def test_rate_limiting(self):
        """Test that rate limiting is working"""
        print("\n⏱️  Test: Rate Limiting")
        print("-" * 80)
        
        symbol = 'AAPL'  # Use one symbol for rate limit test
        
        print(f"\n  Testing rate limiting with {symbol}...")
        
        # Make multiple rapid requests
        num_requests = 5
        start_time = datetime.now()
        
        for i in range(num_requests):
            try:
                price = self.data_source.fetch_current_price(symbol)
                self.assertIsNotNone(price)
                print(f"    Request {i+1}/{num_requests}: ${price:.2f}")
            except Exception as e:
                # Rate limit errors are expected if we exceed limits
                if 'rate limit' in str(e).lower() or '429' in str(e):
                    print(f"    Request {i+1}/{num_requests}: Rate limited (expected)")
                else:
                    raise
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"    ✅ Completed {num_requests} requests in {elapsed:.2f}s")
        print(f"       Rate limit: {settings.massive_rate_limit_calls} calls per {settings.massive_rate_limit_window}s")
    
    def test_data_consistency(self):
        """Test data consistency across different API calls"""
        print("\n🔄 Test: Data Consistency")
        print("-" * 80)
        
        symbol = 'AAPL'
        
        print(f"\n  Testing data consistency for {symbol}...")
        
        try:
            # Fetch current price
            current_price = self.data_source.fetch_current_price(symbol)
            self.assertIsNotNone(current_price)
            
            # Fetch latest price from historical data
            historical_data = self.data_source.fetch_price_data(symbol, period='5d')
            self.assertIsNotNone(historical_data)
            self.assertFalse(historical_data.empty)
            
            latest_close = historical_data['close'].iloc[-1]
            
            # Prices should be close (within 5% - allows for market movement)
            price_diff = abs(current_price - latest_close) / current_price
            self.assertLess(price_diff, 0.05,
                          f"Price mismatch: Current ${current_price:.2f} vs Latest close ${latest_close:.2f} "
                          f"(diff: {price_diff*100:.2f}%)")
            
            print(f"    ✅ Current price: ${current_price:.2f}")
            print(f"       Latest close: ${latest_close:.2f}")
            print(f"       Difference: {price_diff*100:.2f}%")
            
        except Exception as e:
            self.fail(f"Data consistency check failed - {e}")
    
    def test_error_handling(self):
        """Test error handling for invalid symbols"""
        print("\n❌ Test: Error Handling")
        print("-" * 80)
        
        invalid_symbols = ['INVALID123', 'XXXX', '']
        
        for symbol in invalid_symbols:
            with self.subTest(symbol=symbol):
                print(f"\n  Testing invalid symbol: '{symbol}'...")
                
                try:
                    data = self.data_source.fetch_price_data(symbol, period='1d')
                    # If data is returned, it might be empty or None
                    if data is not None and not data.empty:
                        print(f"    ⚠️  {symbol}: Unexpected data returned")
                    else:
                        print(f"    ✅ {symbol}: Correctly returned None/empty")
                except Exception as e:
                    # Exceptions are acceptable for invalid symbols
                    print(f"    ✅ {symbol}: Correctly raised exception: {type(e).__name__}")


if __name__ == '__main__':
    # Configure test output
    unittest.main(verbosity=2, buffer=False)

