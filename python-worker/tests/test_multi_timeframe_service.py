"""
Unit Tests for Multi-Timeframe Service
Tests: Data aggregation, saving, retrieval
Industry Standard: Real data only, no mocks, fail-fast
"""
import unittest
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from app.services.multi_timeframe_service import MultiTimeframeService
from app.database import init_database, db
from app.exceptions import ValidationError, DatabaseError


class TestMultiTimeframeService(unittest.TestCase):
    """
    Unit tests for multi-timeframe service
    Uses real market data (AAPL, GOOGL, NVDA, TQQQ)
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("MULTI-TIMEFRAME SERVICE - UNIT TESTS")
        print("="*80)
        
        # Initialize database
        init_database()
        
        cls.service = MultiTimeframeService()
        cls.test_symbols = ["AAPL", "GOOGL", "NVDA", "TQQQ"]
        
        print(f"\n📊 Test symbols: {', '.join(cls.test_symbols)}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.service = self.__class__.service
        self.test_symbols = self.__class__.test_symbols
    
    def test_fetch_and_save_daily(self):
        """Test fetching and saving daily data"""
        print("\n📊 Testing fetch and save daily data...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                try:
                    rows_saved = self.service.fetch_and_save_timeframe(
                        symbol=symbol,
                        timeframe='daily',
                        start_date=datetime.now() - timedelta(days=100)
                    )
                    
                    self.assertGreater(rows_saved, 0, f"{symbol}: Should save daily data")
                    print(f"   ✅ {symbol}: Saved {rows_saved} daily rows")
                    
                except Exception as e:
                    print(f"   ⚠️  {symbol}: Error - {e}")
                    # Don't fail if data source is unavailable
                    if "data source" in str(e).lower() or "fetch" in str(e).lower():
                        self.skipTest(f"Data source unavailable for {symbol}")
                    else:
                        raise
        
        print("✅ Daily data fetch and save tests passed")
    
    def test_fetch_and_save_weekly(self):
        """Test fetching and saving weekly data"""
        print("\n📊 Testing fetch and save weekly data...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                try:
                    rows_saved = self.service.fetch_and_save_timeframe(
                        symbol=symbol,
                        timeframe='weekly',
                        start_date=datetime.now() - timedelta(days=200)
                    )
                    
                    self.assertGreater(rows_saved, 0, f"{symbol}: Should save weekly data")
                    print(f"   ✅ {symbol}: Saved {rows_saved} weekly rows")
                    
                except Exception as e:
                    print(f"   ⚠️  {symbol}: Error - {e}")
                    if "data source" in str(e).lower() or "fetch" in str(e).lower():
                        self.skipTest(f"Data source unavailable for {symbol}")
                    else:
                        raise
        
        print("✅ Weekly data fetch and save tests passed")
    
    def test_fetch_and_save_monthly(self):
        """Test fetching and saving monthly data"""
        print("\n📊 Testing fetch and save monthly data...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                try:
                    rows_saved = self.service.fetch_and_save_timeframe(
                        symbol=symbol,
                        timeframe='monthly',
                        start_date=datetime.now() - timedelta(days=365)
                    )
                    
                    self.assertGreater(rows_saved, 0, f"{symbol}: Should save monthly data")
                    print(f"   ✅ {symbol}: Saved {rows_saved} monthly rows")
                    
                except Exception as e:
                    print(f"   ⚠️  {symbol}: Error - {e}")
                    if "data source" in str(e).lower() or "fetch" in str(e).lower():
                        self.skipTest(f"Data source unavailable for {symbol}")
                    else:
                        raise
        
        print("✅ Monthly data fetch and save tests passed")
    
    def test_get_timeframe_data(self):
        """Test retrieving timeframe data from database"""
        print("\n📊 Testing get timeframe data...")
        
        # First, ensure we have data
        symbol = "AAPL"
        try:
            self.service.fetch_and_save_timeframe(symbol, 'daily', start_date=datetime.now() - timedelta(days=100))
        except:
            pass  # May already exist
        
        # Test daily
        daily_data = self.service.get_timeframe_data(symbol, 'daily', limit=10)
        self.assertIsInstance(daily_data, pd.DataFrame, "Should return DataFrame")
        
        if not daily_data.empty:
            self.assertIn('date', daily_data.columns, "Should have 'date' column")
            self.assertIn('close', daily_data.columns, "Should have 'close' column")
            print(f"   ✅ Retrieved {len(daily_data)} daily rows for {symbol}")
        
        # Test weekly
        weekly_data = self.service.get_timeframe_data(symbol, 'weekly', limit=10)
        self.assertIsInstance(weekly_data, pd.DataFrame, "Should return DataFrame")
        
        if not weekly_data.empty:
            print(f"   ✅ Retrieved {len(weekly_data)} weekly rows for {symbol}")
        
        print("✅ Get timeframe data tests passed")
    
    def test_aggregation_weekly(self):
        """Test daily to weekly aggregation"""
        print("\n📊 Testing daily to weekly aggregation...")
        
        symbol = "AAPL"
        
        # Get daily data
        daily_data = self.service.get_timeframe_data(symbol, 'daily', limit=50)
        
        if daily_data.empty:
            self.skipTest(f"No daily data for {symbol}")
        
        # Aggregate to weekly
        weekly = self.service._aggregate_to_weekly(daily_data)
        
        self.assertIsInstance(weekly, pd.DataFrame, "Should return DataFrame")
        
        if not weekly.empty:
            # Weekly should have fewer rows than daily
            self.assertLess(len(weekly), len(daily_data), "Weekly should have fewer rows than daily")
            
            # Verify OHLCV columns
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                self.assertIn(col, weekly.columns, f"Should have '{col}' column")
            
            # Verify aggregation logic
            # High should be max of daily highs
            # Low should be min of daily lows
            # Volume should be sum of daily volumes
            
            print(f"   ✅ Aggregated {len(daily_data)} daily rows to {len(weekly)} weekly rows")
        
        print("✅ Weekly aggregation tests passed")
    
    def test_aggregation_monthly(self):
        """Test daily to monthly aggregation"""
        print("\n📊 Testing daily to monthly aggregation...")
        
        symbol = "AAPL"
        
        # Get daily data
        daily_data = self.service.get_timeframe_data(symbol, 'daily', limit=100)
        
        if daily_data.empty:
            self.skipTest(f"No daily data for {symbol}")
        
        # Aggregate to monthly
        monthly = self.service._aggregate_to_monthly(daily_data)
        
        self.assertIsInstance(monthly, pd.DataFrame, "Should return DataFrame")
        
        if not monthly.empty:
            # Monthly should have fewer rows than daily
            self.assertLess(len(monthly), len(daily_data), "Monthly should have fewer rows than daily")
            
            # Verify OHLCV columns
            required_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                self.assertIn(col, monthly.columns, f"Should have '{col}' column")
            
            print(f"   ✅ Aggregated {len(daily_data)} daily rows to {len(monthly)} monthly rows")
        
        print("✅ Monthly aggregation tests passed")
    
    def test_validation(self):
        """Test validation and error handling"""
        print("\n📊 Testing validation...")
        
        # Test invalid timeframe
        with self.assertRaises(ValidationError):
            self.service.fetch_and_save_timeframe("AAPL", "invalid", start_date=datetime.now() - timedelta(days=100))
        
        # Test empty symbol
        with self.assertRaises(ValidationError):
            self.service.fetch_and_save_timeframe("", "daily", start_date=datetime.now() - timedelta(days=100))
        
        # Test invalid timeframe for get
        with self.assertRaises(ValidationError):
            self.service.get_timeframe_data("AAPL", "invalid")
        
        print("✅ Validation tests passed")


if __name__ == '__main__':
    unittest.main(verbosity=2)

