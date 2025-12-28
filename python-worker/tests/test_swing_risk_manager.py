"""
Unit Tests for Swing Risk Manager
Tests: Position sizing, portfolio heat, account balance
Industry Standard: Real data only, no mocks, fail-fast
"""
import unittest
import sys
import os
from pathlib import Path
import uuid
from datetime import datetime, date

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.swing_risk_manager import SwingRiskManager
from app.database import init_database, db
from app.exceptions import ValidationError, DatabaseError


class TestSwingRiskManager(unittest.TestCase):
    """
    Unit tests for swing risk manager
    Uses real database with test data
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("SWING RISK MANAGER - UNIT TESTS")
        print("="*80)
        
        # Initialize database
        init_database()
        
        cls.risk_manager = SwingRiskManager()
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
        
        # Add test holdings
        for symbol in ["AAPL", "GOOGL", "NVDA"]:
            holding_id = f"holding_{portfolio_id}_{symbol}_{int(datetime.now().timestamp() * 1000000)}"
            query = """
                INSERT OR REPLACE INTO holdings
                (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, purchase_date, current_value)
                VALUES (:holding_id, :portfolio_id, :symbol, :quantity, :price, :position_type, :purchase_date, :current_value)
            """
            db.execute_update(query, {
                "holding_id": holding_id,
                "portfolio_id": portfolio_id,
                "symbol": symbol,
                "quantity": 10.0,
                "price": 100.0,
                "position_type": "long",
                "purchase_date": date.today(),
                "current_value": 1000.0  # 10 shares * $100
            })
        
        print(f"\n📊 Test user: {cls.test_user_id}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.risk_manager = self.__class__.risk_manager
        self.test_user_id = self.__class__.test_user_id
    
    def test_position_sizing(self):
        """Test position sizing calculation"""
        print("\n📊 Testing position sizing...")
        
        position = self.risk_manager.calculate_position_size(
            user_id=self.test_user_id,
            entry_price=100.0,
            stop_loss=98.0,
            risk_per_trade=0.01  # 1%
        )
        
        # Verify structure
        self.assertIn('position_size_pct', position, "Should have position_size_pct")
        self.assertIn('position_value', position, "Should have position_value")
        self.assertIn('shares', position, "Should have shares")
        self.assertIn('risk_amount', position, "Should have risk_amount")
        
        # Verify values
        self.assertGreater(position['position_size_pct'], 0, "Position size should be positive")
        self.assertLessEqual(position['position_size_pct'], 0.10, "Position size should be <= 10%")
        self.assertGreater(position['shares'], 0, "Shares should be positive")
        self.assertGreater(position['risk_amount'], 0, "Risk amount should be positive")
        
        print(f"   Position Size: {position['position_size_pct']*100:.1f}%")
        print(f"   Position Value: ${position['position_value']:,.2f}")
        print(f"   Shares: {position['shares']}")
        print(f"   Risk Amount: ${position['risk_amount']:,.2f}")
        
        print("✅ Position sizing tests passed")
    
    def test_position_sizing_validation(self):
        """Test position sizing validation"""
        print("\n📊 Testing position sizing validation...")
        
        # Test invalid entry price
        with self.assertRaises(ValidationError):
            self.risk_manager.calculate_position_size(
                user_id=self.test_user_id,
                entry_price=-100.0,
                stop_loss=98.0
            )
        
        # Test invalid stop loss
        with self.assertRaises(ValidationError):
            self.risk_manager.calculate_position_size(
                user_id=self.test_user_id,
                entry_price=100.0,
                stop_loss=-98.0
            )
        
        # Test invalid risk per trade
        with self.assertRaises(ValidationError):
            self.risk_manager.calculate_position_size(
                user_id=self.test_user_id,
                entry_price=100.0,
                stop_loss=98.0,
                risk_per_trade=0.15  # > 10%
            )
        
        # Test empty user_id
        with self.assertRaises(ValidationError):
            self.risk_manager.calculate_position_size(
                user_id="",
                entry_price=100.0,
                stop_loss=98.0
            )
        
        print("✅ Position sizing validation tests passed")
    
    def test_portfolio_heat(self):
        """Test portfolio heat management"""
        print("\n📊 Testing portfolio heat...")
        
        # Create a separate test user with no holdings to test default balance
        test_user_no_holdings = f"test_user_no_holdings_{int(datetime.now().timestamp() * 1000000)}"
        portfolio_id = f"portfolio_{test_user_no_holdings}_{str(uuid.uuid4())[:8]}"
        query = """
            INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name)
            VALUES (:portfolio_id, :user_id, :portfolio_name)
        """
        db.execute_update(query, {
            "portfolio_id": portfolio_id,
            "user_id": test_user_no_holdings,
            "portfolio_name": "Test Portfolio No Holdings"
        })
        
        # Check portfolio heat with no open trades and no holdings (should use default $100k balance)
        heat = self.risk_manager.check_portfolio_heat(
            user_id=test_user_no_holdings,
            new_trade_risk=500.0
        )
        
        # Verify structure
        self.assertIn('allowed', heat, "Should have 'allowed' key")
        self.assertIn('current_risk', heat, "Should have 'current_risk' key")
        self.assertIn('max_risk', heat, "Should have 'max_risk' key")
        self.assertIn('open_trades', heat, "Should have 'open_trades' key")
        
        # Debug: Print all values
        print(f"   DEBUG - Allowed: {heat['allowed']}")
        print(f"   DEBUG - Current Risk: ${heat['current_risk']:,.2f}")
        print(f"   DEBUG - Total Risk: ${heat['total_risk']:,.2f}")
        print(f"   DEBUG - Max Risk: ${heat['max_risk']:,.2f}")
        print(f"   DEBUG - Account Balance (calculated): ${heat['max_risk'] / 0.05:,.2f}")
        print(f"   DEBUG - Open Trades: {heat['open_trades']}")
        print(f"   DEBUG - Max Open Trades: {heat['max_open_trades']}")
        print(f"   DEBUG - Risk Check: {heat['total_risk']} <= {heat['max_risk']} = {heat['total_risk'] <= heat['max_risk']}")
        print(f"   DEBUG - Trades Check: {heat['open_trades']} < {heat['max_open_trades']} = {heat['open_trades'] < heat['max_open_trades']}")
        
        # With no open trades, should be allowed
        self.assertTrue(heat['allowed'], f"Should be allowed with no open trades. Total risk: {heat['total_risk']}, Max risk: {heat['max_risk']}, Open trades: {heat['open_trades']}, Max open trades: {heat['max_open_trades']}")
        self.assertEqual(heat['current_risk'], 0, "Current risk should be 0")
        self.assertEqual(heat['open_trades'], 0, "Open trades should be 0")
        
        print(f"   Allowed: {heat['allowed']}")
        print(f"   Current Risk: ${heat['current_risk']:,.2f} ({heat['current_risk_pct']:.1f}%)")
        print(f"   Max Risk: ${heat['max_risk']:,.2f} ({heat['max_risk_pct']:.1f}%)")
        print(f"   Open Trades: {heat['open_trades']}/{heat['max_open_trades']}")
        
        print("✅ Portfolio heat tests passed")
    
    def test_portfolio_heat_validation(self):
        """Test portfolio heat validation"""
        print("\n📊 Testing portfolio heat validation...")
        
        # Test empty user_id
        with self.assertRaises(ValidationError):
            self.risk_manager.check_portfolio_heat(
                user_id="",
                new_trade_risk=500.0
            )
        
        # Test negative risk
        with self.assertRaises(ValidationError):
            self.risk_manager.check_portfolio_heat(
                user_id=self.test_user_id,
                new_trade_risk=-500.0
            )
        
        print("✅ Portfolio heat validation tests passed")
    
    def test_account_balance(self):
        """Test account balance calculation"""
        print("\n📊 Testing account balance...")
        
        balance = self.risk_manager._get_account_balance(self.test_user_id)
        
        # Should have balance from test holdings (3 holdings * $1000 = $3000)
        self.assertGreater(balance, 0, "Account balance should be positive")
        
        print(f"   Account Balance: ${balance:,.2f}")
        print("✅ Account balance tests passed")
    
    def test_open_trades(self):
        """Test open trades tracking"""
        print("\n📊 Testing open trades...")
        
        # Create a test swing trade
        trade_id = f"trade_{self.test_user_id}_{str(uuid.uuid4())[:8]}"
        query = """
            INSERT OR REPLACE INTO swing_trades
            (trade_id, user_id, stock_symbol, strategy_name, entry_date, entry_price,
             position_size, stop_loss, take_profit, status)
            VALUES (:trade_id, :user_id, :symbol, :strategy, :entry_date, :entry_price,
                    :position_size, :stop_loss, :take_profit, 'open')
        """
        db.execute_update(query, {
            "trade_id": trade_id,
            "user_id": self.test_user_id,
            "symbol": "AAPL",
            "strategy": "swing_trend",
            "entry_date": date.today(),
            "entry_price": 100.0,
            "position_size": 5.0,  # 5% of portfolio
            "stop_loss": 98.0,
            "take_profit": 106.0
        })
        
        # Get open trades
        open_trades = self.risk_manager._get_open_trades(self.test_user_id)
        
        self.assertIsInstance(open_trades, list, "Should return list")
        self.assertGreater(len(open_trades), 0, "Should have at least one open trade")
        
        # Verify trade structure
        trade = open_trades[0]
        self.assertIn('trade_id', trade, "Trade should have trade_id")
        self.assertIn('symbol', trade, "Trade should have symbol")
        self.assertIn('risk_amount', trade, "Trade should have risk_amount")
        
        print(f"   Open Trades: {len(open_trades)}")
        print(f"   Trade Risk: ${trade['risk_amount']:,.2f}")
        
        # Cleanup
        query = "DELETE FROM swing_trades WHERE trade_id = :trade_id"
        db.execute_update(query, {"trade_id": trade_id})
        
        print("✅ Open trades tests passed")


if __name__ == '__main__':
    unittest.main(verbosity=2)

