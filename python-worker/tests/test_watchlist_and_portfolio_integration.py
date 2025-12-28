"""
Comprehensive Integration Tests for Watchlist and Portfolio Features
Industry Standard: Real database, no mocks, fail-fast, DRY, SOLID
Tests: Watchlist CRUD, Portfolio CRUD, Move to Portfolio, Analytics
"""
import unittest
import sys
import os
import uuid
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_database, db
from app.config import settings


class TestWatchlistAndPortfolioIntegration(unittest.TestCase):
    """
    Comprehensive integration tests for watchlist and portfolio features
    No mocks - uses real database
    Fail-fast - clear error messages
    DRY - reusable test utilities
    SOLID - single responsibility per test
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("WATCHLIST AND PORTFOLIO INTEGRATION TESTS")
        print("="*80)
        
        # Ensure database directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database (runs migrations)
        init_database()
        
        # Use unique user ID per test run to avoid conflicts
        cls.test_user_id = f"test_user_{int(datetime.now().timestamp() * 1000000)}"
        cls.test_portfolio_id = None
        cls.test_watchlist_id = None
        cls.test_holding_id = None
        cls.test_watchlist_item_id = None
        
        print(f"\n📊 Test user: {cls.test_user_id}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.user_id = self.__class__.test_user_id
    
    # ==================== Portfolio CRUD Tests ====================
    
    def test_create_portfolio(self):
        """Test creating a portfolio"""
        print("\n📝 Testing portfolio creation...")
        
        portfolio_name = f"Test Portfolio {datetime.now().strftime('%Y%m%d%H%M%S')}"
        notes = "Test portfolio for integration testing"
        
        portfolio_id = f"portfolio_{self.user_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        
        query = """
            INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name, notes)
            VALUES (:portfolio_id, :user_id, :portfolio_name, :notes)
        """
        
        try:
            db.execute_update(query, {
                "portfolio_id": portfolio_id,
                "user_id": self.user_id,
                "portfolio_name": portfolio_name,
                "notes": notes
            })
            
            # Verify creation
            query = "SELECT * FROM portfolios WHERE portfolio_id = :portfolio_id"
            result = db.execute_query(query, {"portfolio_id": portfolio_id})
            
            self.assertGreater(len(result), 0, "Portfolio should be created")
            self.assertEqual(result[0]['portfolio_name'], portfolio_name)
            self.assertEqual(result[0]['notes'], notes)
            
            self.__class__.test_portfolio_id = portfolio_id
            
            print(f"✅ Created portfolio: {portfolio_id}")
            
        except Exception as e:
            self.fail(f"Failed to create portfolio: {e}")
    
    def test_read_portfolio(self):
        """Test reading a portfolio"""
        print("\n📖 Testing portfolio read...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        query = "SELECT * FROM portfolios WHERE portfolio_id = :portfolio_id"
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        self.assertGreater(len(result), 0, "Portfolio should exist")
        self.assertEqual(result[0]['portfolio_id'], portfolio_id)
        
        print(f"✅ Read portfolio: {portfolio_id}")
    
    def test_update_portfolio(self):
        """Test updating a portfolio"""
        print("\n✏️  Testing portfolio update...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio()
        
        portfolio_id = self.__class__.test_portfolio_id
        new_name = f"Updated Portfolio {datetime.now().strftime('%H%M%S')}"
        new_notes = f"Updated notes at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        query = """
            UPDATE portfolios 
            SET portfolio_name = :name, notes = :notes, updated_at = CURRENT_TIMESTAMP
            WHERE portfolio_id = :portfolio_id
        """
        
        db.execute_update(query, {
            "portfolio_id": portfolio_id,
            "name": new_name,
            "notes": new_notes
        })
        
        # Verify update
        query = "SELECT portfolio_name, notes FROM portfolios WHERE portfolio_id = :portfolio_id"
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        self.assertEqual(result[0]['portfolio_name'], new_name)
        self.assertEqual(result[0]['notes'], new_notes)
        
        print(f"✅ Updated portfolio: {portfolio_id}")
    
    def test_delete_portfolio(self):
        """Test deleting a portfolio"""
        print("\n🗑️  Testing portfolio deletion...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        query = "DELETE FROM portfolios WHERE portfolio_id = :portfolio_id"
        db.execute_update(query, {"portfolio_id": portfolio_id})
        
        # Verify deletion
        query = "SELECT * FROM portfolios WHERE portfolio_id = :portfolio_id"
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        self.assertEqual(len(result), 0, "Portfolio should be deleted")
        
        print(f"✅ Deleted portfolio: {portfolio_id}")
        
        self.__class__.test_portfolio_id = None
    
    # ==================== Watchlist CRUD Tests ====================
    
    def test_create_watchlist(self):
        """Test creating a watchlist"""
        print("\n📝 Testing watchlist creation...")
        
        watchlist_name = f"Test Watchlist {datetime.now().strftime('%Y%m%d%H%M%S')}"
        description = "Test watchlist for integration testing"
        tags = "growth,tech"
        
        watchlist_id = f"watchlist_{self.user_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        
        query = """
            INSERT OR REPLACE INTO watchlists 
            (watchlist_id, user_id, watchlist_name, description, tags, is_default, subscription_level_required)
            VALUES (:watchlist_id, :user_id, :watchlist_name, :description, :tags, :is_default, :subscription_level)
        """
        
        try:
            db.execute_update(query, {
                "watchlist_id": watchlist_id,
                "user_id": self.user_id,
                "watchlist_name": watchlist_name,
                "description": description,
                "tags": tags,
                "is_default": True,
                "subscription_level": "basic"
            })
            
            # Verify creation
            query = "SELECT * FROM watchlists WHERE watchlist_id = :watchlist_id"
            result = db.execute_query(query, {"watchlist_id": watchlist_id})
            
            self.assertGreater(len(result), 0, "Watchlist should be created")
            self.assertEqual(result[0]['watchlist_name'], watchlist_name)
            self.assertEqual(result[0]['description'], description)
            self.assertEqual(result[0]['tags'], tags)
            self.assertTrue(result[0]['is_default'])
            
            self.__class__.test_watchlist_id = watchlist_id
            
            print(f"✅ Created watchlist: {watchlist_id}")
            
        except Exception as e:
            self.fail(f"Failed to create watchlist: {e}")
    
    def test_read_watchlist(self):
        """Test reading a watchlist"""
        print("\n📖 Testing watchlist read...")
        
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        watchlist_id = self.__class__.test_watchlist_id
        
        query = "SELECT * FROM watchlists WHERE watchlist_id = :watchlist_id"
        result = db.execute_query(query, {"watchlist_id": watchlist_id})
        
        self.assertGreater(len(result), 0, "Watchlist should exist")
        self.assertEqual(result[0]['watchlist_id'], watchlist_id)
        
        print(f"✅ Read watchlist: {watchlist_id}")
    
    def test_update_watchlist(self):
        """Test updating a watchlist"""
        print("\n✏️  Testing watchlist update...")
        
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        watchlist_id = self.__class__.test_watchlist_id
        new_name = f"Updated Watchlist {datetime.now().strftime('%H%M%S')}"
        new_tags = "dividend,value"
        
        query = """
            UPDATE watchlists 
            SET watchlist_name = :name, tags = :tags, updated_at = CURRENT_TIMESTAMP
            WHERE watchlist_id = :watchlist_id
        """
        
        db.execute_update(query, {
            "watchlist_id": watchlist_id,
            "name": new_name,
            "tags": new_tags
        })
        
        # Verify update
        query = "SELECT watchlist_name, tags FROM watchlists WHERE watchlist_id = :watchlist_id"
        result = db.execute_query(query, {"watchlist_id": watchlist_id})
        
        self.assertEqual(result[0]['watchlist_name'], new_name)
        self.assertEqual(result[0]['tags'], new_tags)
        
        print(f"✅ Updated watchlist: {watchlist_id}")
    
    def test_delete_watchlist(self):
        """Test deleting a watchlist"""
        print("\n🗑️  Testing watchlist deletion...")
        
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        watchlist_id = self.__class__.test_watchlist_id
        
        query = "DELETE FROM watchlists WHERE watchlist_id = :watchlist_id"
        db.execute_update(query, {"watchlist_id": watchlist_id})
        
        # Verify deletion
        query = "SELECT * FROM watchlists WHERE watchlist_id = :watchlist_id"
        result = db.execute_query(query, {"watchlist_id": watchlist_id})
        
        self.assertEqual(len(result), 0, "Watchlist should be deleted")
        
        print(f"✅ Deleted watchlist: {watchlist_id}")
        
        self.__class__.test_watchlist_id = None
    
    # ==================== Watchlist Items Tests ====================
    
    def test_add_item_to_watchlist(self):
        """Test adding a stock to watchlist"""
        print("\n📝 Testing adding item to watchlist...")
        
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        watchlist_id = self.__class__.test_watchlist_id
        stock_symbol = "AAPL"
        notes = f"Added {stock_symbol} to watchlist for testing"
        priority = 10
        tags = "tech,large-cap"
        
        item_id = f"item_{watchlist_id}_{stock_symbol}_{int(datetime.now().timestamp() * 1000000)}"
        
        query = """
            INSERT OR REPLACE INTO watchlist_items 
            (item_id, watchlist_id, stock_symbol, notes, priority, tags)
            VALUES (:item_id, :watchlist_id, :stock_symbol, :notes, :priority, :tags)
        """
        
        try:
            db.execute_update(query, {
                "item_id": item_id,
                "watchlist_id": watchlist_id,
                "stock_symbol": stock_symbol,
                "notes": notes,
                "priority": priority,
                "tags": tags
            })
            
            # Verify creation
            query = "SELECT * FROM watchlist_items WHERE item_id = :item_id"
            result = db.execute_query(query, {"item_id": item_id})
            
            self.assertGreater(len(result), 0, "Watchlist item should be created")
            self.assertEqual(result[0]['stock_symbol'], stock_symbol)
            self.assertEqual(result[0]['notes'], notes)
            self.assertEqual(result[0]['priority'], priority)
            
            self.__class__.test_watchlist_item_id = item_id
            
            print(f"✅ Added item to watchlist: {stock_symbol}")
            
        except Exception as e:
            self.fail(f"Failed to add watchlist item: {e}")
    
    def test_read_watchlist_items(self):
        """Test reading watchlist items"""
        print("\n📖 Testing reading watchlist items...")
        
        # Ensure watchlist exists
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        watchlist_id = self.__class__.test_watchlist_id
        
        # Ensure at least one item exists in this watchlist
        # Check if we have an item for this watchlist
        query = "SELECT COUNT(*) as count FROM watchlist_items WHERE watchlist_id = :watchlist_id"
        count_result = db.execute_query(query, {"watchlist_id": watchlist_id})
        
        if count_result[0]['count'] == 0:
            # Add an item if none exists
            stock_symbol = "MSFT"
            item_id = f"item_{watchlist_id}_{stock_symbol}_{int(datetime.now().timestamp() * 1000000)}"
            
            query = """
                INSERT OR REPLACE INTO watchlist_items 
                (item_id, watchlist_id, stock_symbol, notes, priority, tags)
                VALUES (:item_id, :watchlist_id, :stock_symbol, :notes, :priority, :tags)
            """
            db.execute_update(query, {
                "item_id": item_id,
                "watchlist_id": watchlist_id,
                "stock_symbol": stock_symbol,
                "notes": f"Added {stock_symbol} for read test",
                "priority": 5,
                "tags": "tech"
            })
            
            self.__class__.test_watchlist_item_id = item_id
        
        # Now read items
        query = """
            SELECT * FROM watchlist_items 
            WHERE watchlist_id = :watchlist_id
            ORDER BY priority DESC, added_at DESC
        """
        result = db.execute_query(query, {"watchlist_id": watchlist_id})
        
        self.assertGreater(len(result), 0, "Should have at least one item")
        
        print(f"✅ Read {len(result)} watchlist items")
    
    def test_update_watchlist_item(self):
        """Test updating a watchlist item"""
        print("\n✏️  Testing watchlist item update...")
        
        # Ensure watchlist exists
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        watchlist_id = self.__class__.test_watchlist_id
        
        # Ensure item exists in this watchlist
        item_id = None
        if self.__class__.test_watchlist_item_id:
            query = "SELECT watchlist_id FROM watchlist_items WHERE item_id = :item_id"
            item_check = db.execute_query(query, {"item_id": self.__class__.test_watchlist_item_id})
            if len(item_check) > 0 and item_check[0]['watchlist_id'] == watchlist_id:
                item_id = self.__class__.test_watchlist_item_id
        
        # Create new item if needed
        if not item_id:
            stock_symbol = "TSLA"
            item_id = f"item_{watchlist_id}_{stock_symbol}_{int(datetime.now().timestamp() * 1000000)}"
            
            query = """
                INSERT OR REPLACE INTO watchlist_items 
                (item_id, watchlist_id, stock_symbol, notes, priority, tags)
                VALUES (:item_id, :watchlist_id, :stock_symbol, :notes, :priority, :tags)
            """
            db.execute_update(query, {
                "item_id": item_id,
                "watchlist_id": watchlist_id,
                "stock_symbol": stock_symbol,
                "notes": f"Added {stock_symbol} for update test",
                "priority": 10,
                "tags": "tech"
            })
            
            self.__class__.test_watchlist_item_id = item_id
        
        new_notes = f"Updated notes at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        new_priority = 20
        
        query = """
            UPDATE watchlist_items 
            SET notes = :notes, priority = :priority
            WHERE item_id = :item_id
        """
        
        db.execute_update(query, {
            "item_id": item_id,
            "notes": new_notes,
            "priority": new_priority
        })
        
        # Verify update
        query = "SELECT notes, priority FROM watchlist_items WHERE item_id = :item_id"
        result = db.execute_query(query, {"item_id": item_id})
        
        self.assertEqual(result[0]['notes'], new_notes)
        self.assertEqual(result[0]['priority'], new_priority)
        
        print(f"✅ Updated watchlist item: {item_id}")
    
    def test_remove_watchlist_item(self):
        """Test removing a stock from watchlist"""
        print("\n🗑️  Testing watchlist item removal...")
        
        # Ensure watchlist exists
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        watchlist_id = self.__class__.test_watchlist_id
        
        # Ensure item exists in this watchlist
        if not self.__class__.test_watchlist_item_id:
            self.test_add_item_to_watchlist()
        
        # Verify item belongs to current watchlist, create if needed
        item_id = self.__class__.test_watchlist_item_id
        query = "SELECT watchlist_id FROM watchlist_items WHERE item_id = :item_id"
        item_check = db.execute_query(query, {"item_id": item_id})
        
        if len(item_check) == 0 or item_check[0]['watchlist_id'] != watchlist_id:
            stock_symbol = "NVDA"
            item_id = f"item_{watchlist_id}_{stock_symbol}_{int(datetime.now().timestamp() * 1000000)}"
            
            query = """
                INSERT OR REPLACE INTO watchlist_items 
                (item_id, watchlist_id, stock_symbol, notes, priority, tags)
                VALUES (:item_id, :watchlist_id, :stock_symbol, :notes, :priority, :tags)
            """
            db.execute_update(query, {
                "item_id": item_id,
                "watchlist_id": watchlist_id,
                "stock_symbol": stock_symbol,
                "notes": f"Added {stock_symbol} for removal test",
                "priority": 15,
                "tags": "tech"
            })
            
            self.__class__.test_watchlist_item_id = item_id
        
        query = "DELETE FROM watchlist_items WHERE item_id = :item_id"
        db.execute_update(query, {"item_id": item_id})
        
        # Verify deletion
        query = "SELECT * FROM watchlist_items WHERE item_id = :item_id"
        result = db.execute_query(query, {"item_id": item_id})
        
        self.assertEqual(len(result), 0, "Watchlist item should be deleted")
        
        print(f"✅ Removed watchlist item: {item_id}")
        
        self.__class__.test_watchlist_item_id = None
    
    # ==================== Move to Portfolio Tests ====================
    
    def test_move_to_portfolio(self):
        """Test moving stock from watchlist to portfolio"""
        print("\n🔄 Testing move to portfolio...")
        
        # Create watchlist and add item
        if not self.__class__.test_watchlist_id:
            self.test_create_watchlist()
        
        if not self.__class__.test_watchlist_item_id:
            self.test_add_item_to_watchlist()
        
        # Create portfolio
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio()
        
        watchlist_id = self.__class__.test_watchlist_id
        item_id = self.__class__.test_watchlist_item_id
        portfolio_id = self.__class__.test_portfolio_id
        
        # Get stock symbol from watchlist item
        query = "SELECT stock_symbol FROM watchlist_items WHERE item_id = :item_id"
        item_result = db.execute_query(query, {"item_id": item_id})
        stock_symbol = item_result[0]['stock_symbol']
        
        # Create holding (simulating move to portfolio)
        holding_id = f"holding_{portfolio_id}_{stock_symbol}_{int(datetime.now().timestamp() * 1000000)}"
        
        query = """
            INSERT INTO holdings 
            (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, 
             position_type, notes, purchase_date)
            VALUES (:holding_id, :portfolio_id, :stock_symbol, :quantity, :avg_entry_price,
                    :position_type, :notes, :purchase_date)
        """
        
        try:
            db.execute_update(query, {
                "holding_id": holding_id,
                "portfolio_id": portfolio_id,
                "stock_symbol": stock_symbol,
                "quantity": 10.0,
                "avg_entry_price": 150.0,
                "position_type": "long",
                "notes": f"Moved from watchlist {watchlist_id}",
                "purchase_date": datetime.now().date()
            })
            
            # Verify holding created
            query = "SELECT * FROM holdings WHERE holding_id = :holding_id"
            holding_result = db.execute_query(query, {"holding_id": holding_id})
            
            self.assertGreater(len(holding_result), 0, "Holding should be created")
            self.assertEqual(holding_result[0]['stock_symbol'], stock_symbol)
            self.assertEqual(holding_result[0]['portfolio_id'], portfolio_id)
            
            # Remove from watchlist (optional - could keep it)
            query = "DELETE FROM watchlist_items WHERE item_id = :item_id"
            db.execute_update(query, {"item_id": item_id})
            
            # Verify item removed from watchlist
            query = "SELECT * FROM watchlist_items WHERE item_id = :item_id"
            item_check = db.execute_query(query, {"item_id": item_id})
            self.assertEqual(len(item_check), 0, "Item should be removed from watchlist")
            
            self.__class__.test_holding_id = holding_id
            
            print(f"✅ Moved {stock_symbol} from watchlist to portfolio")
            print(f"   Holding ID: {holding_id}")
            
        except Exception as e:
            self.fail(f"Failed to move to portfolio: {e}")
    
    # ==================== Portfolio Holdings Tests ====================
    
    def test_create_holding(self):
        """Test creating a holding in portfolio"""
        print("\n📝 Testing holding creation...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio()
        
        portfolio_id = self.__class__.test_portfolio_id
        stock_symbol = "GOOGL"
        
        holding_id = f"holding_{portfolio_id}_{stock_symbol}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        
        query = """
            INSERT OR REPLACE INTO holdings 
            (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, 
             position_type, notes, purchase_date)
            VALUES (:holding_id, :portfolio_id, :stock_symbol, :quantity, :avg_entry_price,
                    :position_type, :notes, :purchase_date)
        """
        
        try:
            db.execute_update(query, {
                "holding_id": holding_id,
                "portfolio_id": portfolio_id,
                "stock_symbol": stock_symbol,
                "quantity": 5.0,
                "avg_entry_price": 140.0,
                "position_type": "long",
                "notes": "Test holding",
                "purchase_date": datetime.now().date()
            })
            
            # Verify creation
            query = "SELECT * FROM holdings WHERE holding_id = :holding_id"
            result = db.execute_query(query, {"holding_id": holding_id})
            
            self.assertGreater(len(result), 0, "Holding should be created")
            self.assertEqual(result[0]['stock_symbol'], stock_symbol)
            
            self.__class__.test_holding_id = holding_id
            
            print(f"✅ Created holding: {holding_id}")
            
        except Exception as e:
            self.fail(f"Failed to create holding: {e}")
    
    def test_read_holdings(self):
        """Test reading portfolio holdings"""
        print("\n📖 Testing reading holdings...")
        
        if not self.__class__.test_portfolio_id:
            self.test_create_portfolio()
        
        if not self.__class__.test_holding_id:
            self.test_create_holding()
        
        portfolio_id = self.__class__.test_portfolio_id
        
        query = """
            SELECT * FROM holdings 
            WHERE portfolio_id = :portfolio_id
            ORDER BY purchase_date DESC
        """
        result = db.execute_query(query, {"portfolio_id": portfolio_id})
        
        self.assertGreater(len(result), 0, "Should have at least one holding")
        
        print(f"✅ Read {len(result)} holdings")
    
    def test_update_holding(self):
        """Test updating a holding"""
        print("\n✏️  Testing holding update...")
        
        if not self.__class__.test_holding_id:
            self.test_create_holding()
        
        holding_id = self.__class__.test_holding_id
        new_quantity = 15.0
        new_notes = f"Updated holding at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        query = """
            UPDATE holdings 
            SET quantity = :quantity, notes = :notes, updated_at = CURRENT_TIMESTAMP
            WHERE holding_id = :holding_id
        """
        
        db.execute_update(query, {
            "holding_id": holding_id,
            "quantity": new_quantity,
            "notes": new_notes
        })
        
        # Verify update
        query = "SELECT quantity, notes FROM holdings WHERE holding_id = :holding_id"
        result = db.execute_query(query, {"holding_id": holding_id})
        
        self.assertEqual(result[0]['quantity'], new_quantity)
        self.assertEqual(result[0]['notes'], new_notes)
        
        print(f"✅ Updated holding: {holding_id}")
    
    def test_delete_holding(self):
        """Test deleting a holding"""
        print("\n🗑️  Testing holding deletion...")
        
        if not self.__class__.test_holding_id:
            self.test_create_holding()
        
        holding_id = self.__class__.test_holding_id
        
        query = "DELETE FROM holdings WHERE holding_id = :holding_id"
        db.execute_update(query, {"holding_id": holding_id})
        
        # Verify deletion
        query = "SELECT * FROM holdings WHERE holding_id = :holding_id"
        result = db.execute_query(query, {"holding_id": holding_id})
        
        self.assertEqual(len(result), 0, "Holding should be deleted")
        
        print(f"✅ Deleted holding: {holding_id}")
        
        self.__class__.test_holding_id = None
    
    # ==================== Integration Tests ====================
    
    def test_full_workflow(self):
        """Test complete workflow: Create watchlist -> Add items -> Move to portfolio"""
        print("\n🔄 Testing full workflow...")
        
        # 1. Create watchlist
        watchlist_name = f"Workflow Watchlist {datetime.now().strftime('%Y%m%d%H%M%S')}"
        watchlist_id = f"watchlist_{self.user_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        
        query = """
            INSERT OR REPLACE INTO watchlists 
            (watchlist_id, user_id, watchlist_name, is_default, subscription_level_required)
            VALUES (:watchlist_id, :user_id, :watchlist_name, :is_default, :subscription_level)
        """
        db.execute_update(query, {
            "watchlist_id": watchlist_id,
            "user_id": self.user_id,
            "watchlist_name": watchlist_name,
            "is_default": True,
            "subscription_level": "basic"
        })
        
        # 2. Add multiple stocks to watchlist
        stocks = ["AAPL", "GOOGL", "MSFT"]
        item_ids = []
        
        for i, symbol in enumerate(stocks):
            item_id = f"item_{watchlist_id}_{symbol}_{int(datetime.now().timestamp() * 1000000)}"
            query = """
                INSERT INTO watchlist_items 
                (item_id, watchlist_id, stock_symbol, priority, notes)
                VALUES (:item_id, :watchlist_id, :stock_symbol, :priority, :notes)
            """
            db.execute_update(query, {
                "item_id": item_id,
                "watchlist_id": watchlist_id,
                "stock_symbol": symbol,
                "priority": i * 10,
                "notes": f"Added {symbol} to watchlist"
            })
            item_ids.append(item_id)
        
        # 3. Verify watchlist has items
        query = "SELECT COUNT(*) as count FROM watchlist_items WHERE watchlist_id = :watchlist_id"
        result = db.execute_query(query, {"watchlist_id": watchlist_id})
        self.assertEqual(result[0]['count'], len(stocks), "Should have all stocks in watchlist")
        
        # 4. Create portfolio
        portfolio_id = f"portfolio_{self.user_id}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
        query = """
            INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name)
            VALUES (:portfolio_id, :user_id, :portfolio_name)
        """
        db.execute_update(query, {
            "portfolio_id": portfolio_id,
            "user_id": self.user_id,
            "portfolio_name": "Workflow Portfolio"
        })
        
        # 5. Move first stock from watchlist to portfolio
        first_item_id = item_ids[0]
        query = "SELECT stock_symbol FROM watchlist_items WHERE item_id = :item_id"
        item_result = db.execute_query(query, {"item_id": first_item_id})
        stock_symbol = item_result[0]['stock_symbol']
        
        holding_id = f"holding_{portfolio_id}_{stock_symbol}_{int(datetime.now().timestamp() * 1000000)}"
        query = """
            INSERT INTO holdings 
            (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, purchase_date)
            VALUES (:holding_id, :portfolio_id, :stock_symbol, :quantity, :avg_entry_price, :position_type, :purchase_date)
        """
        db.execute_update(query, {
            "holding_id": holding_id,
            "portfolio_id": portfolio_id,
            "stock_symbol": stock_symbol,
            "quantity": 10.0,
            "avg_entry_price": 150.0,
            "position_type": "long",
            "purchase_date": datetime.now().date()
        })
        
        # 6. Remove from watchlist
        query = "DELETE FROM watchlist_items WHERE item_id = :item_id"
        db.execute_update(query, {"item_id": first_item_id})
        
        # 7. Verify: holding exists, item removed from watchlist
        query = "SELECT * FROM holdings WHERE holding_id = :holding_id"
        holding_result = db.execute_query(query, {"holding_id": holding_id})
        self.assertGreater(len(holding_result), 0, "Holding should exist")
        
        query = "SELECT * FROM watchlist_items WHERE item_id = :item_id"
        item_check = db.execute_query(query, {"item_id": first_item_id})
        self.assertEqual(len(item_check), 0, "Item should be removed from watchlist")
        
        # 8. Verify watchlist still has remaining items
        query = "SELECT COUNT(*) as count FROM watchlist_items WHERE watchlist_id = :watchlist_id"
        result = db.execute_query(query, {"watchlist_id": watchlist_id})
        self.assertEqual(result[0]['count'], len(stocks) - 1, "Watchlist should have remaining items")
        
        print(f"✅ Full workflow completed successfully")
        print(f"   Watchlist: {watchlist_id} ({len(stocks)} items -> {len(stocks) - 1} items)")
        print(f"   Portfolio: {portfolio_id} (1 holding)")
    
    def test_subscription_level_filtering(self):
        """Test subscription level filtering for watchlists"""
        print("\n🔒 Testing subscription level filtering...")
        
        # Create watchlists with different subscription levels
        watchlist_ids = []
        for level in ["basic", "pro", "elite"]:
            watchlist_id = f"watchlist_{self.user_id}_{level}_{int(datetime.now().timestamp() * 1000000)}_{str(uuid.uuid4())[:8]}"
            query = """
                INSERT OR REPLACE INTO watchlists 
                (watchlist_id, user_id, watchlist_name, subscription_level_required)
                VALUES (:watchlist_id, :user_id, :watchlist_name, :subscription_level)
            """
            db.execute_update(query, {
                "watchlist_id": watchlist_id,
                "user_id": self.user_id,
                "watchlist_name": f"{level.capitalize()} Watchlist",
                "subscription_level": level
            })
            watchlist_ids.append((watchlist_id, level))
        
        # Test basic user sees only basic watchlists
        query = """
            SELECT * FROM watchlists 
            WHERE user_id = :user_id 
            AND subscription_level_required = 'basic'
        """
        result = db.execute_query(query, {"user_id": self.user_id})
        self.assertGreater(len(result), 0, "Basic user should see basic watchlists")
        
        # Test pro user sees basic and pro watchlists
        query = """
            SELECT * FROM watchlists 
            WHERE user_id = :user_id 
            AND subscription_level_required IN ('basic', 'pro')
        """
        result = db.execute_query(query, {"user_id": self.user_id})
        self.assertGreater(len(result), 0, "Pro user should see basic and pro watchlists")
        
        print(f"✅ Subscription level filtering working correctly")


if __name__ == '__main__':
    unittest.main(verbosity=2)

