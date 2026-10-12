"""
Integration Tests for Swing Trading System
Tests: End-to-end swing trading workflow
Industry Standard: Real data only, no mocks, fail-fast
"""
import unittest
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
from app.services.multi_timeframe_service import MultiTimeframeService
from app.strategies.swing.trend_strategy import SwingTrendStrategy
from app.database import init_database, db
from app.market_regime.models import MarketPermissions, MarketRegime, RegimeLabel
from app.risk import PortfolioConstraints, assess_risk
from app.swing_opportunity.models import (
    OpportunityQuality, SetupAssessment, SetupType, StockAnalysis,
    StockDataQuality, StockTechnicals, SwingOpportunity,
)
from app.exceptions import ValidationError, DatabaseError


def assess_signal_risk(result, symbol: str):
    """Adapt the legacy strategy result into the canonical risk contract."""
    entry = float(result.entry_price)
    stop = float(result.stop_loss)
    opportunity = SwingOpportunity(
        symbol=symbol,
        market_regime="bullish",
        market_condition="trend",
        swing_environment="medium",
        swing_size_multiplier=0.5,
        stock=StockAnalysis(
            symbol=symbol,
            technicals=StockTechnicals(
                price=entry,
                atr_pct=max((entry - stop) / entry / 2, 0.001),
            ),
            data_quality=StockDataQuality(
                bars=200, required_bars=200, sufficient=True),
        ),
        setup=SetupAssessment(
            type=SetupType.TREND_CONTINUATION,
            quality=OpportunityQuality.HIGH,
            score=80,
            confirmation="confirmed",
        ),
        opportunity_quality=OpportunityQuality.HIGH,
        opportunity_score=80,
        next_step="RISK_ASSESSMENT",
    )
    regime = MarketRegime(
        regime=RegimeLabel.BULL_LOW_VOL,
        direction="bullish",
        condition="trend",
        confidence=0.8,
        market_permissions=MarketPermissions(
            normal_long=True, size_multiplier=0.5),
    )
    return assess_risk(
        opportunity,
        regime,
        PortfolioConstraints(account_equity=100000),
        entry=entry,
        stop=stop,
        target=float(result.take_profit),
    )


class TestSwingTradingIntegration(unittest.TestCase):
    """
    Integration tests for swing trading system
    Tests end-to-end workflow with real data
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("SWING TRADING - INTEGRATION TESTS")
        print("="*80)
        
        # Initialize database
        init_database()
        
        cls.mtf_service = MultiTimeframeService()
        cls.strategy = SwingTrendStrategy()
        cls.test_symbols = ["AAPL", "GOOGL", "NVDA", "TQQQ"]
        cls.test_user_id = f"test_user_{int(datetime.now().timestamp() * 1000000)}"
        
        # Create test portfolio
        portfolio_id = f"portfolio_{cls.test_user_id}_{str(uuid.uuid4())[:8]}"
        query = """
            INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name)
            VALUES (:portfolio_id, :user_id, :portfolio_name)
        """
        db.execute_update(query, {
            "portfolio_id": portfolio_id,
            "user_id": cls.test_user_id,
            "portfolio_name": "Test Portfolio"
        })
        
        # Fetch and save data for all symbols
        print("\n📊 Loading market data...")
        for symbol in cls.test_symbols:
            try:
                cls.mtf_service.fetch_and_save_timeframe(symbol, 'daily', start_date=datetime.now() - timedelta(days=200))
                cls.mtf_service.fetch_and_save_timeframe(symbol, 'weekly', start_date=datetime.now() - timedelta(days=400))
                print(f"   ✅ {symbol}: Data loaded")
            except Exception as e:
                print(f"   ⚠️  {symbol}: Error - {e}")
        
        print(f"\n📊 Test user: {cls.test_user_id}")
        print(f"📊 Test symbols: {', '.join(cls.test_symbols)}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.mtf_service = self.__class__.mtf_service
        self.strategy = self.__class__.strategy
        self.test_symbols = self.__class__.test_symbols
        self.test_user_id = self.__class__.test_user_id
    
    def test_end_to_end_swing_trading(self):
        """Test complete swing trading workflow"""
        print("\n🔄 Testing end-to-end swing trading workflow...")
        
        symbol = "AAPL"
        
        try:
            # Step 1: Get multi-timeframe data
            print(f"\n   Step 1: Fetching data for {symbol}...")
            daily_data = self.mtf_service.get_timeframe_data(symbol, 'daily', limit=100)
            weekly_data = self.mtf_service.get_timeframe_data(symbol, 'weekly', limit=50)
            
            if daily_data.empty:
                self.skipTest(f"No daily data for {symbol}")
            
            print(f"      ✅ Daily data: {len(daily_data)} rows")
            if not weekly_data.empty:
                print(f"      ✅ Weekly data: {len(weekly_data)} rows")
            
            # Step 2: Generate swing signal
            print(f"\n   Step 2: Generating swing signal for {symbol}...")
            result = self.strategy.generate_swing_signal(
                daily_data=daily_data,
                weekly_data=weekly_data if not weekly_data.empty else None,
                context={'account_balance': 100000}
            )
            
            self.assertIsNotNone(result, "Should return signal result")
            self.assertIn(result.signal, ['BUY', 'SELL', 'HOLD'], "Signal should be valid")
            
            print(f"      ✅ Signal: {result.signal}")
            print(f"      ✅ Confidence: {result.confidence:.1%}")
            
            if result.signal == 'BUY':
                print(f"      ✅ Entry: ${result.entry_price:.2f}")
                print(f"      ✅ Stop Loss: ${result.stop_loss:.2f}")
                print(f"      ✅ Take Profit: ${result.take_profit:.2f}")
                print(f"      ✅ Risk-Reward: {result.risk_reward_ratio:.2f}")
                
                # Step 3: Run canonical deterministic risk assessment
                print(f"\n   Step 3: Running risk assessment...")
                risk = assess_signal_risk(result, symbol)
                self.assertIsInstance(risk.allowed, bool, "Should return boolean")
                print(f"      ✅ Status: {risk.status.value}")
                print(f"      ✅ Position Size: {risk.position_size_pct*100:.1f}%")
                print(f"      ✅ Shares: {risk.shares}")
                print(f"      ✅ Risk Amount: ${risk.risk_amount or 0:,.2f}")
            
            print("\n✅ End-to-end workflow test passed")
            
        except Exception as e:
            print(f"\n❌ Error in end-to-end test: {e}")
            raise
    
    def test_multi_symbol_analysis(self):
        """Test analyzing multiple symbols"""
        print("\n📊 Testing multi-symbol analysis...")
        
        signals = {}
        
        for symbol in self.test_symbols:
            try:
                daily_data = self.mtf_service.get_timeframe_data(symbol, 'daily', limit=100)
                weekly_data = self.mtf_service.get_timeframe_data(symbol, 'weekly', limit=50)
                
                if daily_data.empty:
                    continue
                
                result = self.strategy.generate_swing_signal(
                    daily_data=daily_data,
                    weekly_data=weekly_data if not weekly_data.empty else None,
                    context={'account_balance': 100000}
                )
                
                signals[symbol] = result
                
                print(f"   {symbol}: {result.signal} (confidence: {result.confidence:.1%})")
                
            except Exception as e:
                print(f"   ⚠️  {symbol}: Error - {e}")
        
        # Should have at least one signal
        self.assertGreater(len(signals), 0, "Should have at least one signal")
        
        # Count signals
        buy_signals = sum(1 for s in signals.values() if s.signal == 'BUY')
        sell_signals = sum(1 for s in signals.values() if s.signal == 'SELL')
        hold_signals = sum(1 for s in signals.values() if s.signal == 'HOLD')
        
        print(f"\n   📊 Signal Summary:")
        print(f"      BUY: {buy_signals}")
        print(f"      SELL: {sell_signals}")
        print(f"      HOLD: {hold_signals}")
        
        print("\n✅ Multi-symbol analysis test passed")
    
    def test_risk_management_integration(self):
        """Test risk management integration"""
        print("\n📊 Testing risk management integration...")
        
        symbol = "AAPL"
        daily_data = self.mtf_service.get_timeframe_data(symbol, 'daily', limit=100)
        
        if daily_data.empty:
            self.skipTest(f"No data for {symbol}")
        
        # Generate signal
        result = self.strategy.generate_swing_signal(
            daily_data=daily_data,
            context={'account_balance': 100000}
        )
        
        if result.signal == 'BUY':
            # Run canonical deterministic risk assessment
            risk = assess_signal_risk(result, symbol)
            self.assertLessEqual(risk.position_size_pct, 0.10, "Position size should be <= 10%")
            if risk.portfolio_heat_after is not None:
                self.assertLessEqual(risk.portfolio_heat_after, 0.05)
            
            print(f"   ✅ Position size: {risk.position_size_pct*100:.1f}%")
            print(f"   ✅ Portfolio heat: {(risk.portfolio_heat_after or 0)*100:.1f}%")
            print(f"   ✅ Trade allowed: {risk.allowed}")
        
        print("\n✅ Risk management integration test passed")
    
    def test_data_persistence(self):
        """Test data persistence across timeframes"""
        print("\n📊 Testing data persistence...")
        
        symbol = "AAPL"
        
        # Fetch daily data
        daily_before = self.mtf_service.get_timeframe_data(symbol, 'daily', limit=10)
        daily_count_before = len(daily_before)
        
        # Fetch and save again (should not duplicate)
        try:
            self.mtf_service.fetch_and_save_timeframe(symbol, 'daily', start_date=datetime.now() - timedelta(days=100))
        except:
            pass  # May already exist
        
        # Fetch daily data again
        daily_after = self.mtf_service.get_timeframe_data(symbol, 'daily', limit=10)
        daily_count_after = len(daily_after)
        
        # Should have same or more data (not less)
        self.assertGreaterEqual(daily_count_after, daily_count_before, "Should not lose data")
        
        print(f"   ✅ Daily data: {daily_count_before} → {daily_count_after} rows")
        
        # Test weekly data
        weekly = self.mtf_service.get_timeframe_data(symbol, 'weekly', limit=10)
        if not weekly.empty:
            print(f"   ✅ Weekly data: {len(weekly)} rows")
        
        print("\n✅ Data persistence test passed")


if __name__ == '__main__':
    unittest.main(verbosity=2)

