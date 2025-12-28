"""
Unit Tests for Swing Trend Strategy
Tests: Signal generation, entry/exit conditions, multi-timeframe analysis
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
from app.strategies.swing.trend_strategy import SwingTrendStrategy
from app.services.multi_timeframe_service import MultiTimeframeService
from app.database import init_database
from app.exceptions import ValidationError


class TestSwingTrendStrategy(unittest.TestCase):
    """
    Unit tests for swing trend strategy
    Uses real market data (AAPL, GOOGL, NVDA, TQQQ)
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("SWING TREND STRATEGY - UNIT TESTS")
        print("="*80)
        
        # Initialize database
        init_database()
        
        cls.strategy = SwingTrendStrategy()
        cls.mtf_service = MultiTimeframeService()
        cls.test_symbols = ["AAPL", "GOOGL", "NVDA", "TQQQ"]
        
        # Fetch and save data for all symbols
        for symbol in cls.test_symbols:
            try:
                cls.mtf_service.fetch_and_save_timeframe(symbol, 'daily', start_date=datetime.now() - timedelta(days=200))
                cls.mtf_service.fetch_and_save_timeframe(symbol, 'weekly', start_date=datetime.now() - timedelta(days=400))
            except Exception as e:
                print(f"⚠️  Error loading data for {symbol}: {e}")
        
        print(f"\n📊 Test symbols: {', '.join(cls.test_symbols)}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.strategy = self.__class__.strategy
        self.mtf_service = self.__class__.mtf_service
        self.test_symbols = self.__class__.test_symbols
    
    def test_signal_generation(self):
        """Test signal generation with real data"""
        print("\n📊 Testing signal generation...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                try:
                    # Get daily and weekly data
                    daily_data = self.mtf_service.get_timeframe_data(symbol, 'daily', limit=100)
                    weekly_data = self.mtf_service.get_timeframe_data(symbol, 'weekly', limit=50)
                    
                    if daily_data.empty:
                        self.skipTest(f"No daily data for {symbol}")
                    
                    # Generate signal
                    result = self.strategy.generate_swing_signal(
                        daily_data=daily_data,
                        weekly_data=weekly_data if not weekly_data.empty else None,
                        context={'account_balance': 100000}
                    )
                    
                    # Verify result structure
                    self.assertIsNotNone(result, f"{symbol}: Should return result")
                    self.assertIn(result.signal, ['BUY', 'SELL', 'HOLD'], f"{symbol}: Signal should be BUY/SELL/HOLD")
                    self.assertIsInstance(result.confidence, float, f"{symbol}: Confidence should be float")
                    self.assertGreaterEqual(result.confidence, 0.0, f"{symbol}: Confidence should be >= 0")
                    self.assertLessEqual(result.confidence, 1.0, f"{symbol}: Confidence should be <= 1")
                    
                    print(f"   {symbol}: Signal = {result.signal}, Confidence = {result.confidence:.1%}")
                    if result.signal == 'BUY':
                        print(f"      Entry: ${result.entry_price:.2f}, Stop: ${result.stop_loss:.2f}, Target: ${result.take_profit:.2f}")
                        print(f"      Position Size: {result.position_size*100:.1f}%, Risk-Reward: {result.risk_reward_ratio:.2f}")
                    
                except Exception as e:
                    print(f"   ⚠️  {symbol}: Error - {e}")
                    if "insufficient" in str(e).lower():
                        self.skipTest(f"Insufficient data for {symbol}")
                    else:
                        raise
        
        print("✅ Signal generation tests passed")
    
    def test_entry_conditions(self):
        """Test entry condition validation"""
        print("\n📊 Testing entry conditions...")
        
        symbol = "AAPL"
        daily_data = self.mtf_service.get_timeframe_data(symbol, 'daily', limit=100)
        weekly_data = self.mtf_service.get_timeframe_data(symbol, 'weekly', limit=50)
        
        if daily_data.empty:
            self.skipTest(f"No data for {symbol}")
        
        result = self.strategy.generate_swing_signal(
            daily_data=daily_data,
            weekly_data=weekly_data if not weekly_data.empty else None,
            context={'account_balance': 100000}
        )
        
        # If BUY signal, verify entry conditions
        if result.signal == 'BUY':
            self.assertGreater(result.entry_price, 0, "Entry price should be positive")
            self.assertGreater(result.stop_loss, 0, "Stop loss should be positive")
            self.assertGreater(result.take_profit, result.entry_price, "Take profit should be > entry")
            self.assertLess(result.stop_loss, result.entry_price, "Stop loss should be < entry")
            self.assertGreater(result.risk_reward_ratio, 0, "Risk-reward ratio should be positive")
            self.assertGreater(result.confidence, 0.5, "BUY signal should have confidence > 0.5")
        
        print("✅ Entry conditions tests passed")
    
    def test_insufficient_data(self):
        """Test handling of insufficient data"""
        print("\n📊 Testing insufficient data handling...")
        
        # Create minimal data
        minimal_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=10, freq='D'),
            'open': [100] * 10,
            'high': [105] * 10,
            'low': [95] * 10,
            'close': [100] * 10,
            'volume': [1000000] * 10
        })
        
        result = self.strategy.generate_swing_signal(daily_data=minimal_data)
        
        # Should return HOLD with low confidence
        self.assertEqual(result.signal, 'HOLD', "Should return HOLD for insufficient data")
        self.assertEqual(result.confidence, 0.0, "Confidence should be 0 for insufficient data")
        
        print("✅ Insufficient data handling tests passed")
    
    def test_validation(self):
        """Test validation and error handling"""
        print("\n📊 Testing validation...")
        
        # Test empty data
        with self.assertRaises(ValidationError):
            self.strategy.generate_swing_signal(daily_data=pd.DataFrame())
        
        # Test None data
        with self.assertRaises(ValidationError):
            self.strategy.generate_swing_signal(daily_data=None)
        
        print("✅ Validation tests passed")
    
    def test_position_sizing(self):
        """Test position sizing calculation"""
        print("\n📊 Testing position sizing...")
        
        # Test position sizing
        position_size = self.strategy.calculate_position_size(
            entry_price=100.0,
            stop_loss=98.0,
            account_balance=100000.0,
            risk_per_trade=0.01  # 1%
        )
        
        self.assertGreater(position_size, 0, "Position size should be positive")
        self.assertLessEqual(position_size, 0.10, "Position size should be <= 10%")
        
        # Risk amount should be 1% of account
        risk_amount = 100000.0 * 0.01  # $1000
        price_risk = 100.0 - 98.0  # $2
        expected_shares = int(risk_amount / price_risk)  # 500 shares
        expected_position_value = expected_shares * 100.0  # $50,000
        expected_position_size = expected_position_value / 100000.0  # 50%
        
        # Should be capped at 10%
        self.assertLessEqual(position_size, 0.10, "Position size should be capped at 10%")
        
        print(f"   Position size: {position_size*100:.1f}%")
        print("✅ Position sizing tests passed")
    
    def test_risk_reward_calculation(self):
        """Test risk-reward ratio calculation"""
        print("\n📊 Testing risk-reward calculation...")
        
        risk_reward = self.strategy.calculate_risk_reward(
            entry_price=100.0,
            stop_loss=98.0,
            take_profit=106.0
        )
        
        # Risk = $2, Reward = $6, Ratio = 3:1
        expected_ratio = 6.0 / 2.0  # 3.0
        
        self.assertAlmostEqual(risk_reward, expected_ratio, places=2, msg="Risk-reward ratio should be 3.0")
        
        print(f"   Risk-reward ratio: {risk_reward:.2f}")
        print("✅ Risk-reward calculation tests passed")


if __name__ == '__main__':
    unittest.main(verbosity=2)

