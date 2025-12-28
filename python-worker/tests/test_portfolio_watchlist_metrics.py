"""
Integration Tests for Portfolio and Watchlist Metrics Calculation
Tests: All new fields are populated correctly with real data
Industry Standard: Real database, no mocks, fail-fast, DRY, SOLID
"""
import unittest
import sys
import os
import uuid
from datetime import datetime, date
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_database, db
from app.services.portfolio_calculator import PortfolioCalculatorService
from app.services.watchlist_calculator import WatchlistCalculatorService
from app.config import settings


class TestPortfolioWatchlistMetrics(unittest.TestCase):
    """
    Comprehensive tests for portfolio and watchlist metrics calculation
    Tests all new fields are populated correctly
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("PORTFOLIO AND WATCHLIST METRICS INTEGRATION TESTS")
        print("="*80)
        
        # Ensure database directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database (runs migrations)
        init_database()
        
        cls.portfolio_calculator = PortfolioCalculatorService()
        cls.watchlist_calculator = WatchlistCalculatorService()
        
        # Use unique user ID per test run
        cls.test_user_id = f"test_user_{int(datetime.now().timestamp() * 1000000)}"
        cls.test_portfolio_id = None
        cls.test_holding_id = None
        cls.test_watchlist_id = None
        cls.test_watchlist_item_id = None
        
        print(f"\n📊 Test user: {cls.test_user_id}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.user_id = self.__class__.test_user_id
        self.portfolio_calculator = self.__class__.portfolio_calculator
        self.watchlist_calculator = self.__class__.watchlist_calculator
    
    # ==================== Portfolio Metrics Tests ====================
    
    def test_update_holding_metrics(self):
        """Test updating holding metrics with real data"""
        print("\n📊 Testing holding metrics calculation...")
        
        # Create portfolio
        portfolio_id = f"portfolio_{self.user_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        query = """
            INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name)
            VALUES (:portfolio_id, :user_id, :portfolio_name)
        """
        db.execute_update(query, {
            "portfolio_id": portfolio_id,
            "user_id": self.user_id,
            "portfolio_name": "Test Portfolio"
        })
        
        # Create holding for AAPL
        holding_id = f"holding_{portfolio_id}_AAPL_{int(datetime.now().timestamp() * 1000000)}"
        query = """
            INSERT OR REPLACE INTO holdings 
            (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, purchase_date)
            VALUES (:holding_id, :portfolio_id, :stock_symbol, :quantity, :avg_entry_price, :position_type, :purchase_date)
        """
        db.execute_update(query, {
            "holding_id": holding_id,
            "portfolio_id": portfolio_id,
            "stock_symbol": "AAPL",
            "quantity": 10.0,
            "avg_entry_price": 150.0,
            "position_type": "long",
            "purchase_date": date.today()
        })
        
        self.__class__.test_portfolio_id = portfolio_id
        self.__class__.test_holding_id = holding_id
        
        # Update metrics
        try:
            success = self.portfolio_calculator.update_holding_metrics(holding_id)
            self.assertTrue(success, "Should successfully update holding metrics")
            
            # Verify metrics were calculated
            query = """
                SELECT current_price, current_value, cost_basis, unrealized_gain_loss, 
                       unrealized_gain_loss_percent, sector, industry, market_cap_category,
                       dividend_yield, allocation_percent, last_updated_price
                FROM holdings WHERE holding_id = :holding_id
            """
            result = db.execute_query(query, {"holding_id": holding_id})
            
            self.assertGreater(len(result), 0, "Holding should exist")
            holding = result[0]
            
            # Verify all fields are populated
            self.assertIsNotNone(holding['current_price'], "Current price should be set")
            self.assertIsNotNone(holding['current_value'], "Current value should be calculated")
            self.assertIsNotNone(holding['cost_basis'], "Cost basis should be calculated")
            self.assertIsNotNone(holding['unrealized_gain_loss'], "Unrealized P&L should be calculated")
            self.assertIsNotNone(holding['unrealized_gain_loss_percent'], "Unrealized P&L % should be calculated")
            
            # Verify calculations are correct
            expected_cost_basis = 10.0 * 150.0
            self.assertEqual(holding['cost_basis'], expected_cost_basis, "Cost basis should be quantity * entry price")
            self.assertEqual(holding['current_value'], holding['current_price'] * 10.0, "Current value should be price * quantity")
            
            print(f"✅ Holding metrics calculated correctly")
            print(f"   Current Price: ${holding['current_price']:.2f}")
            print(f"   Current Value: ${holding['current_value']:.2f}")
            print(f"   Cost Basis: ${holding['cost_basis']:.2f}")
            print(f"   Unrealized P&L: ${holding['unrealized_gain_loss']:.2f} ({holding['unrealized_gain_loss_percent']:.2f}%)")
            print(f"   Sector: {holding.get('sector', 'N/A')}")
            print(f"   Industry: {holding.get('industry', 'N/A')}")
            
        except Exception as e:
            self.fail(f"Failed to update holding metrics: {e}")
    
    def test_calculate_portfolio_performance(self):
        """Test portfolio performance calculation"""
        print("\n📊 Testing portfolio performance calculation...")
        
        if not self.__class__.test_portfolio_id:
            self.test_update_holding_metrics()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        # Calculate performance
        try:
            performance = self.portfolio_calculator.calculate_portfolio_performance(portfolio_id)
            
            # Verify performance metrics
            self.assertIsNotNone(performance.get('total_value'), "Total value should be calculated")
            self.assertIsNotNone(performance.get('cost_basis'), "Cost basis should be calculated")
            self.assertIsNotNone(performance.get('total_gain_loss'), "Total P&L should be calculated")
            self.assertIsNotNone(performance.get('total_gain_loss_percent'), "Total P&L % should be calculated")
            self.assertGreater(performance.get('total_stocks', 0), 0, "Should have at least one stock")
            
            # Verify snapshot was saved
            query = """
                SELECT * FROM portfolio_performance 
                WHERE portfolio_id = :portfolio_id 
                ORDER BY snapshot_date DESC LIMIT 1
            """
            snapshot = db.execute_query(query, {"portfolio_id": portfolio_id})
            self.assertGreater(len(snapshot), 0, "Performance snapshot should be saved")
            
            print(f"✅ Portfolio performance calculated")
            print(f"   Total Value: ${performance['total_value']:.2f}")
            print(f"   Cost Basis: ${performance['cost_basis']:.2f}")
            print(f"   Total P&L: ${performance['total_gain_loss']:.2f} ({performance['total_gain_loss_percent']:.2f}%)")
            print(f"   Stocks: {performance['total_stocks']}")
            
        except Exception as e:
            self.fail(f"Failed to calculate portfolio performance: {e}")
    
    def test_update_all_portfolio_holdings(self):
        """Test updating all holdings in a portfolio"""
        print("\n📊 Testing update all portfolio holdings...")
        
        if not self.__class__.test_portfolio_id:
            self.test_update_holding_metrics()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        # Add another holding
        holding_id2 = f"holding_{portfolio_id}_GOOGL_{int(datetime.now().timestamp() * 1000000)}"
        query = """
            INSERT OR REPLACE INTO holdings 
            (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, purchase_date)
            VALUES (:holding_id, :portfolio_id, :stock_symbol, :quantity, :avg_entry_price, :position_type, :purchase_date)
        """
        db.execute_update(query, {
            "holding_id": holding_id2,
            "portfolio_id": portfolio_id,
            "stock_symbol": "GOOGL",
            "quantity": 5.0,
            "avg_entry_price": 140.0,
            "position_type": "long",
            "purchase_date": date.today()
        })
        
        # Update all holdings
        try:
            updated_count = self.portfolio_calculator.update_portfolio_holdings(portfolio_id)
            self.assertGreater(updated_count, 0, "Should update at least one holding")
            
            # Verify both holdings have metrics
            query = """
                SELECT COUNT(*) as count FROM holdings 
                WHERE portfolio_id = :portfolio_id 
                AND current_price IS NOT NULL
            """
            result = db.execute_query(query, {"portfolio_id": portfolio_id})
            self.assertGreater(result[0]['count'], 0, "Holdings should have current_price set")
            
            print(f"✅ Updated {updated_count} holdings")
            
        except Exception as e:
            self.fail(f"Failed to update portfolio holdings: {e}")
    
    # ==================== Watchlist Metrics Tests ====================
    
    def test_update_watchlist_item_metrics(self):
        """Test updating watchlist item metrics with real data"""
        print("\n📊 Testing watchlist item metrics calculation...")
        
        # Create watchlist
        watchlist_id = f"watchlist_{self.user_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        query = """
            INSERT OR REPLACE INTO watchlists 
            (watchlist_id, user_id, watchlist_name, subscription_level_required)
            VALUES (:watchlist_id, :user_id, :watchlist_name, :subscription_level)
        """
        db.execute_update(query, {
            "watchlist_id": watchlist_id,
            "user_id": self.user_id,
            "watchlist_name": "Test Watchlist",
            "subscription_level": "basic"
        })
        
        # Create watchlist item for NVDA
        item_id = f"item_{watchlist_id}_NVDA_{int(datetime.now().timestamp() * 1000000)}"
        query = """
            INSERT OR REPLACE INTO watchlist_items 
            (item_id, watchlist_id, stock_symbol, priority)
            VALUES (:item_id, :watchlist_id, :stock_symbol, :priority)
        """
        db.execute_update(query, {
            "item_id": item_id,
            "watchlist_id": watchlist_id,
            "stock_symbol": "NVDA",
            "priority": 10
        })
        
        self.__class__.test_watchlist_id = watchlist_id
        self.__class__.test_watchlist_item_id = item_id
        
        # Update metrics
        try:
            success = self.watchlist_calculator.update_watchlist_item_metrics(item_id)
            self.assertTrue(success, "Should successfully update watchlist item metrics")
            
            # Verify metrics were calculated
            query = """
                SELECT current_price, price_when_added, price_change_since_added,
                       price_change_percent_since_added, sector, industry, market_cap_category,
                       dividend_yield, earnings_date, last_updated_price
                FROM watchlist_items WHERE item_id = :item_id
            """
            result = db.execute_query(query, {"item_id": item_id})
            
            self.assertGreater(len(result), 0, "Watchlist item should exist")
            item = result[0]
            
            # Verify all fields are populated
            self.assertIsNotNone(item['current_price'], "Current price should be set")
            self.assertIsNotNone(item['price_when_added'], "Price when added should be set")
            
            # Price change should be calculated (price_when_added is set to current_price on first update)
            # On first update, price_change will be 0 (or very close to 0)
            self.assertIsNotNone(item.get('price_change_since_added'), "Price change should be calculated (can be 0)")
            self.assertIsNotNone(item.get('price_change_percent_since_added'), "Price change % should be calculated (can be 0)")
            
            print(f"✅ Watchlist item metrics calculated correctly")
            print(f"   Current Price: ${item['current_price']:.2f}")
            print(f"   Price When Added: ${item.get('price_when_added', 0):.2f}")
            if item.get('price_change_percent_since_added'):
                print(f"   Change Since Added: {item['price_change_percent_since_added']:.2f}%")
            print(f"   Sector: {item.get('sector', 'N/A')}")
            print(f"   Industry: {item.get('industry', 'N/A')}")
            if item.get('earnings_date'):
                print(f"   Next Earnings: {item['earnings_date']}")
            
        except Exception as e:
            self.fail(f"Failed to update watchlist item metrics: {e}")
    
    def test_calculate_watchlist_performance(self):
        """Test watchlist performance calculation"""
        print("\n📊 Testing watchlist performance calculation...")
        
        if not self.__class__.test_watchlist_id:
            self.test_update_watchlist_item_metrics()
        
        watchlist_id = self.__class__.test_watchlist_id
        
        # Add another item
        item_id2 = f"item_{watchlist_id}_MSFT_{int(datetime.now().timestamp() * 1000000)}"
        query = """
            INSERT OR REPLACE INTO watchlist_items 
            (item_id, watchlist_id, stock_symbol, priority)
            VALUES (:item_id, :watchlist_id, :stock_symbol, :priority)
        """
        db.execute_update(query, {
            "item_id": item_id2,
            "watchlist_id": watchlist_id,
            "stock_symbol": "MSFT",
            "priority": 5
        })
        
        # Update items first
        self.watchlist_calculator.update_watchlist_items(watchlist_id)
        
        # Calculate performance
        try:
            performance = self.watchlist_calculator.calculate_watchlist_performance(watchlist_id)
            
            # Verify performance metrics
            self.assertIsNotNone(performance.get('total_stocks'), "Total stocks should be calculated")
            self.assertGreater(performance.get('total_stocks', 0), 0, "Should have at least one stock")
            
            # Verify snapshot was saved
            query = """
                SELECT * FROM watchlist_performance 
                WHERE watchlist_id = :watchlist_id 
                ORDER BY snapshot_date DESC LIMIT 1
            """
            snapshot = db.execute_query(query, {"watchlist_id": watchlist_id})
            self.assertGreater(len(snapshot), 0, "Performance snapshot should be saved")
            
            print(f"✅ Watchlist performance calculated")
            print(f"   Total Stocks: {performance['total_stocks']}")
            print(f"   Avg Price Change: {performance.get('avg_price_change_percent', 0):.2f}%")
            print(f"   Bullish: {performance.get('bullish_count', 0)}, Bearish: {performance.get('bearish_count', 0)}")
            
        except Exception as e:
            self.fail(f"Failed to calculate watchlist performance: {e}")
    
    def test_update_all_watchlist_items(self):
        """Test updating all items in a watchlist"""
        print("\n📊 Testing update all watchlist items...")
        
        if not self.__class__.test_watchlist_id:
            self.test_update_watchlist_item_metrics()
        
        watchlist_id = self.__class__.test_watchlist_id
        
        # Update all items
        try:
            updated_count = self.watchlist_calculator.update_watchlist_items(watchlist_id)
            self.assertGreater(updated_count, 0, "Should update at least one item")
            
            # Verify items have metrics
            query = """
                SELECT COUNT(*) as count FROM watchlist_items 
                WHERE watchlist_id = :watchlist_id 
                AND current_price IS NOT NULL
            """
            result = db.execute_query(query, {"watchlist_id": watchlist_id})
            self.assertGreater(result[0]['count'], 0, "Items should have current_price set")
            
            print(f"✅ Updated {updated_count} watchlist items")
            
        except Exception as e:
            self.fail(f"Failed to update watchlist items: {e}")
    
    # ==================== Data Completeness Tests ====================
    
    def test_all_holding_fields_populated(self):
        """Test that all new holding fields can be populated"""
        print("\n✅ Testing all holding fields are populated...")
        
        if not self.__class__.test_holding_id:
            self.test_update_holding_metrics()
        
        holding_id = self.__class__.test_holding_id
        
        query = """
            SELECT 
                current_price, current_value, cost_basis,
                unrealized_gain_loss, unrealized_gain_loss_percent,
                sector, industry, market_cap_category, dividend_yield,
                allocation_percent, last_updated_price
            FROM holdings WHERE holding_id = :holding_id
        """
        result = db.execute_query(query, {"holding_id": holding_id})
        
        holding = result[0]
        
        # Check critical fields
        critical_fields = [
            'current_price', 'current_value', 'cost_basis',
            'unrealized_gain_loss', 'unrealized_gain_loss_percent'
        ]
        
        for field in critical_fields:
            self.assertIsNotNone(holding.get(field), f"{field} should be populated")
        
        print(f"✅ All critical holding fields populated")
    
    def test_all_watchlist_item_fields_populated(self):
        """Test that all new watchlist item fields can be populated"""
        print("\n✅ Testing all watchlist item fields are populated...")
        
        if not self.__class__.test_watchlist_item_id:
            self.test_update_watchlist_item_metrics()
        
        item_id = self.__class__.test_watchlist_item_id
        
        query = """
            SELECT 
                current_price, price_when_added,
                price_change_since_added, price_change_percent_since_added,
                sector, industry, market_cap_category, dividend_yield,
                earnings_date, last_updated_price
            FROM watchlist_items WHERE item_id = :item_id
        """
        result = db.execute_query(query, {"item_id": item_id})
        
        item = result[0]
        
        # Check critical fields
        critical_fields = ['current_price', 'price_when_added']
        
        for field in critical_fields:
            self.assertIsNotNone(item.get(field), f"{field} should be populated")
        
        # Price change should be calculated (can be 0 on first update)
        # On first update, price_when_added is set to current_price, so change will be 0
        if item.get('price_when_added') is not None:
            self.assertIsNotNone(item.get('price_change_since_added'), "Price change should be calculated (can be 0)")
            self.assertIsNotNone(item.get('price_change_percent_since_added'), "Price change % should be calculated (can be 0)")
        
        print(f"✅ All critical watchlist item fields populated")
    
    # ==================== Calculation Accuracy Tests ====================
    
    def test_holding_calculations_accuracy(self):
        """Test that holding calculations are mathematically correct"""
        print("\n🧮 Testing holding calculation accuracy...")
        
        if not self.__class__.test_holding_id:
            self.test_update_holding_metrics()
        
        holding_id = self.__class__.test_holding_id
        
        query = """
            SELECT quantity, avg_entry_price, current_price, current_value,
                   cost_basis, unrealized_gain_loss, unrealized_gain_loss_percent
            FROM holdings WHERE holding_id = :holding_id
        """
        result = db.execute_query(query, {"holding_id": holding_id})
        holding = result[0]
        
        quantity = holding['quantity']
        avg_entry_price = holding['avg_entry_price']
        current_price = holding['current_price']
        current_value = holding['current_value']
        cost_basis = holding['cost_basis']
        unrealized_gain_loss = holding['unrealized_gain_loss']
        unrealized_gain_loss_percent = holding['unrealized_gain_loss_percent']
        
        # Verify calculations
        expected_cost_basis = quantity * avg_entry_price
        expected_current_value = quantity * current_price
        expected_unrealized_gain_loss = expected_current_value - expected_cost_basis
        expected_unrealized_gain_loss_percent = (expected_unrealized_gain_loss / expected_cost_basis * 100) if expected_cost_basis > 0 else 0
        
        self.assertAlmostEqual(cost_basis, expected_cost_basis, places=2, msg="Cost basis calculation incorrect")
        self.assertAlmostEqual(current_value, expected_current_value, places=2, msg="Current value calculation incorrect")
        self.assertAlmostEqual(unrealized_gain_loss, expected_unrealized_gain_loss, places=2, msg="Unrealized P&L calculation incorrect")
        self.assertAlmostEqual(unrealized_gain_loss_percent, expected_unrealized_gain_loss_percent, places=2, msg="Unrealized P&L % calculation incorrect")
        
        print(f"✅ All holding calculations are accurate")
    
    def test_watchlist_item_calculations_accuracy(self):
        """Test that watchlist item calculations are mathematically correct"""
        print("\n🧮 Testing watchlist item calculation accuracy...")
        
        if not self.__class__.test_watchlist_item_id:
            self.test_update_watchlist_item_metrics()
        
        item_id = self.__class__.test_watchlist_item_id
        
        query = """
            SELECT current_price, price_when_added,
                   price_change_since_added, price_change_percent_since_added
            FROM watchlist_items WHERE item_id = :item_id
        """
        result = db.execute_query(query, {"item_id": item_id})
        item = result[0]
        
        current_price = item['current_price']
        price_when_added = item.get('price_when_added')
        
        if price_when_added and price_when_added > 0:
            price_change_since_added = item.get('price_change_since_added')
            price_change_percent_since_added = item.get('price_change_percent_since_added')
            
            # Verify calculations
            expected_price_change = current_price - price_when_added
            expected_price_change_percent = (expected_price_change / price_when_added * 100)
            
            self.assertAlmostEqual(price_change_since_added, expected_price_change, places=2, msg="Price change calculation incorrect")
            self.assertAlmostEqual(price_change_percent_since_added, expected_price_change_percent, places=2, msg="Price change % calculation incorrect")
            
            print(f"✅ All watchlist item calculations are accurate")
        else:
            print(f"⚠️  Price when added not set, skipping calculation accuracy test")


if __name__ == '__main__':
    unittest.main(verbosity=2)

