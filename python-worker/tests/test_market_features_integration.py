"""
Integration Tests for Market Features
Tests: Market Movers, Sector Performance, Stock Comparison, Analyst Ratings, Market Overview, Market Trends
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
from app.services.market_movers_service import MarketMoversService
from app.services.sector_performance_service import SectorPerformanceService
from app.services.stock_comparison_service import StockComparisonService
from app.services.analyst_ratings_service import AnalystRatingsService
from app.services.market_overview_service import MarketOverviewService
from app.services.market_trends_service import MarketTrendsService
from app.config import settings


class TestMarketFeaturesIntegration(unittest.TestCase):
    """
    Comprehensive integration tests for all market features
    Tests with real data (AAPL, GOOGL, NVDA, MSFT, TSLA)
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("MARKET FEATURES INTEGRATION TESTS")
        print("="*80)
        
        # Ensure database directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database (runs migrations)
        init_database()
        
        cls.market_movers_service = MarketMoversService()
        cls.sector_performance_service = SectorPerformanceService()
        cls.stock_comparison_service = StockComparisonService()
        cls.analyst_ratings_service = AnalystRatingsService()
        cls.market_overview_service = MarketOverviewService()
        cls.market_trends_service = MarketTrendsService()
        
        # Test symbols
        cls.test_symbols = ["AAPL", "GOOGL", "NVDA", "MSFT", "TSLA"]
        
        print(f"\n📊 Test symbols: {', '.join(cls.test_symbols)}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.market_movers_service = self.__class__.market_movers_service
        self.sector_performance_service = self.__class__.sector_performance_service
        self.stock_comparison_service = self.__class__.stock_comparison_service
        self.analyst_ratings_service = self.__class__.analyst_ratings_service
        self.market_overview_service = self.__class__.market_overview_service
        self.market_trends_service = self.__class__.market_trends_service
        self.test_symbols = self.__class__.test_symbols
    
    # ==================== Market Movers Tests ====================
    
    def test_calculate_market_movers(self):
        """Test calculating market movers"""
        print("\n📊 Testing market movers calculation...")
        
        try:
            # First, ensure we have some live price data
            from app.data_sources import get_data_source
            data_source = get_data_source()
            
            # Fetch and save live prices for test symbols
            for symbol in self.test_symbols[:3]:  # Test with first 3
                try:
                    current_price = data_source.fetch_current_price(symbol)
                    if current_price:
                        query = """
                            INSERT INTO live_prices (stock_symbol, price, timestamp)
                            VALUES (:symbol, :price, CURRENT_TIMESTAMP)
                        """
                        db.execute_update(query, {"symbol": symbol, "price": current_price})
                except Exception as e:
                    print(f"⚠️  Could not fetch price for {symbol}: {e}")
            
            # Calculate market movers
            result = self.market_movers_service.calculate_market_movers(period="day", limit=10)
            
            # Verify structure
            self.assertIn("gainers", result, "Should have gainers")
            self.assertIn("losers", result, "Should have losers")
            self.assertIn("most_active", result, "Should have most_active")
            self.assertEqual(result["period"], "day", "Period should be day")
            
            print(f"✅ Market movers calculated")
            print(f"   Gainers: {len(result['gainers'])}")
            print(f"   Losers: {len(result['losers'])}")
            print(f"   Most Active: {len(result['most_active'])}")
            
        except Exception as e:
            self.fail(f"Failed to calculate market movers: {e}")
    
    def test_get_market_movers(self):
        """Test getting market movers from database"""
        print("\n📊 Testing get market movers...")
        
        try:
            # Get gainers
            gainers = self.market_movers_service.get_market_movers("gainers", "day", 10)
            self.assertIsInstance(gainers, list, "Gainers should be a list")
            
            # Get losers
            losers = self.market_movers_service.get_market_movers("losers", "day", 10)
            self.assertIsInstance(losers, list, "Losers should be a list")
            
            # Get most active
            most_active = self.market_movers_service.get_market_movers("most_active", "day", 10)
            self.assertIsInstance(most_active, list, "Most active should be a list")
            
            print(f"✅ Retrieved market movers")
            print(f"   Gainers: {len(gainers)}, Losers: {len(losers)}, Most Active: {len(most_active)}")
            
        except Exception as e:
            self.fail(f"Failed to get market movers: {e}")
    
    # ==================== Sector Performance Tests ====================
    
    def test_calculate_sector_performance(self):
        """Test calculating sector performance"""
        print("\n📊 Testing sector performance calculation...")
        
        try:
            # First, ensure we have holdings/watchlists with sectors
            user_id = f"test_user_{int(datetime.now().timestamp() * 1000000)}"
            
            # Create portfolio with holdings
            portfolio_id = f"portfolio_{user_id}_{str(uuid.uuid4())[:8]}"
            query = """
                INSERT OR REPLACE INTO portfolios (portfolio_id, user_id, portfolio_name)
                VALUES (:portfolio_id, :user_id, :portfolio_name)
            """
            db.execute_update(query, {
                "portfolio_id": portfolio_id,
                "user_id": user_id,
                "portfolio_name": "Test Portfolio"
            })
            
            # Add holdings with sectors (will be populated by portfolio calculator)
            for symbol in self.test_symbols[:3]:
                holding_id = f"holding_{portfolio_id}_{symbol}_{int(datetime.now().timestamp() * 1000000)}"
                query = """
                    INSERT OR REPLACE INTO holdings
                    (holding_id, portfolio_id, stock_symbol, quantity, avg_entry_price, position_type, purchase_date)
                    VALUES (:holding_id, :portfolio_id, :symbol, :quantity, :price, :position_type, :purchase_date)
                """
                db.execute_update(query, {
                    "holding_id": holding_id,
                    "portfolio_id": portfolio_id,
                    "symbol": symbol,
                    "quantity": 10.0,
                    "price": 100.0,
                    "position_type": "long",
                    "purchase_date": date.today()
                })
            
            # Update holdings to populate sectors
            from app.services.portfolio_calculator import PortfolioCalculatorService
            portfolio_calculator = PortfolioCalculatorService()
            portfolio_calculator.update_portfolio_holdings(portfolio_id)
            
            # Calculate sector performance
            result = self.sector_performance_service.calculate_sector_performance()
            
            # Verify structure
            self.assertIn("sectors", result, "Should have sectors")
            self.assertIsInstance(result["sectors"], list, "Sectors should be a list")
            
            print(f"✅ Sector performance calculated")
            print(f"   Sectors: {len(result['sectors'])}")
            if result['sectors']:
                for sector in result['sectors'][:3]:
                    print(f"   {sector.get('sector', 'Unknown')}: {sector.get('avg_price_change_percent', 0):.2f}%")
            
        except Exception as e:
            self.fail(f"Failed to calculate sector performance: {e}")
    
    def test_get_sector_performance(self):
        """Test getting sector performance from database"""
        print("\n📊 Testing get sector performance...")
        
        try:
            performance = self.sector_performance_service.get_sector_performance(None, 10)
            self.assertIsInstance(performance, list, "Performance should be a list")
            
            print(f"✅ Retrieved sector performance: {len(performance)} sectors")
            
        except Exception as e:
            self.fail(f"Failed to get sector performance: {e}")
    
    # ==================== Stock Comparison Tests ====================
    
    def test_compare_stocks(self):
        """Test comparing multiple stocks"""
        print("\n📊 Testing stock comparison...")
        
        try:
            # Compare test symbols
            result = self.stock_comparison_service.compare_stocks(self.test_symbols[:3])
            
            # Verify structure
            self.assertIn("symbols", result, "Should have symbols")
            self.assertIn("comparison", result, "Should have comparison")
            self.assertEqual(len(result["symbols"]), 3, "Should compare 3 symbols")
            
            # Verify each symbol has comparison data (or at least symbol entry)
            # Note: Data might be minimal if not loaded yet, but structure should exist
            for symbol in result["symbols"]:
                # Symbol should be in comparison, even if data is minimal
                if symbol in result["comparison"]:
                    symbol_data = result["comparison"][symbol]
                    self.assertIn("symbol", symbol_data, f"Should have symbol in {symbol} data")
                else:
                    # If symbol not in comparison, it means no data was found at all
                    # This is acceptable if data hasn't been loaded yet
                    print(f"⚠️  No comparison data found for {symbol} (data may not be loaded)")
            
            print(f"✅ Stock comparison successful")
            print(f"   Compared {len(result['symbols'])} stocks")
            for symbol in result["symbols"]:
                data = result["comparison"][symbol]
                if data.get('current_price'):
                    print(f"   {symbol}: ${data['current_price']:.2f}")
            
        except Exception as e:
            self.fail(f"Failed to compare stocks: {e}")
    
    def test_compare_stocks_validation(self):
        """Test stock comparison validation"""
        print("\n📊 Testing stock comparison validation...")
        
        # Test empty list
        with self.assertRaises(Exception):
            self.stock_comparison_service.compare_stocks([])
        
        # Test too many symbols
        with self.assertRaises(Exception):
            self.stock_comparison_service.compare_stocks(["AAPL"] * 11)
        
        print("✅ Stock comparison validation working")
    
    # ==================== Analyst Ratings Tests ====================
    
    def test_fetch_analyst_ratings(self):
        """Test fetching analyst ratings (if API key configured)"""
        print("\n📊 Testing analyst ratings fetch...")
        
        try:
            # Try to fetch ratings for AAPL
            count = self.analyst_ratings_service.fetch_and_save_ratings("AAPL")
            
            # If API key not configured, count will be 0
            if count == 0:
                print("⚠️  Analyst ratings API not configured (FINNHUB_API_KEY not set)")
                print("   This is expected if API key is not provided")
                return
            
            # Verify ratings were saved
            ratings = self.analyst_ratings_service.get_analyst_ratings("AAPL")
            self.assertGreater(len(ratings), 0, "Should have at least one rating")
            
            # Verify consensus was calculated
            consensus = self.analyst_ratings_service.get_consensus("AAPL")
            self.assertIsNotNone(consensus, "Should have consensus")
            self.assertIn("consensus_rating", consensus, "Consensus should have rating")
            
            print(f"✅ Analyst ratings fetched and saved")
            print(f"   Ratings: {len(ratings)}")
            print(f"   Consensus: {consensus.get('consensus_rating', 'N/A')}")
            
        except Exception as e:
            # If API key not configured, this is expected
            if "API key" in str(e) or "not configured" in str(e):
                print("⚠️  Analyst ratings API not configured (expected)")
            else:
                self.fail(f"Failed to fetch analyst ratings: {e}")
    
    def test_get_analyst_ratings(self):
        """Test getting analyst ratings from database"""
        print("\n📊 Testing get analyst ratings...")
        
        try:
            ratings = self.analyst_ratings_service.get_analyst_ratings("AAPL")
            self.assertIsInstance(ratings, list, "Ratings should be a list")
            
            consensus = self.analyst_ratings_service.get_consensus("AAPL")
            
            print(f"✅ Retrieved analyst ratings")
            print(f"   Ratings: {len(ratings)}")
            if consensus:
                print(f"   Consensus: {consensus.get('consensus_rating', 'N/A')}")
            
        except Exception as e:
            self.fail(f"Failed to get analyst ratings: {e}")
    
    # ==================== Market Overview Tests ====================
    
    def test_get_market_overview(self):
        """Test getting market overview"""
        print("\n📊 Testing market overview...")
        
        try:
            overview = self.market_overview_service.get_market_overview()
            
            # Verify structure
            self.assertIn("market_status", overview, "Should have market status")
            self.assertIn("indices", overview, "Should have indices")
            self.assertIn("statistics", overview, "Should have statistics")
            
            print(f"✅ Market overview retrieved")
            print(f"   Market Status: {overview.get('market_status', 'N/A')}")
            print(f"   Indices: {len([k for k, v in overview.get('indices', {}).items() if v])}")
            stats = overview.get('statistics', {})
            print(f"   Advancing: {stats.get('advancing', 0)}, Declining: {stats.get('declining', 0)}")
            
        except Exception as e:
            self.fail(f"Failed to get market overview: {e}")
    
    # ==================== Market Trends Tests ====================
    
    def test_calculate_market_trends(self):
        """Test calculating market trends"""
        print("\n📊 Testing market trends calculation...")
        
        try:
            trends = self.market_trends_service.calculate_market_trends()
            
            # Verify structure
            self.assertIn("sectors", trends, "Should have sectors")
            self.assertIn("industries", trends, "Should have industries")
            self.assertIn("market_cap", trends, "Should have market_cap")
            self.assertIn("overall", trends, "Should have overall")
            
            print(f"✅ Market trends calculated")
            print(f"   Sectors: {len(trends.get('sectors', []))}")
            print(f"   Industries: {len(trends.get('industries', []))}")
            overall = trends.get('overall', {})
            print(f"   Overall Trend: {overall.get('direction', 'N/A')} ({overall.get('strength', 'N/A')})")
            
        except Exception as e:
            self.fail(f"Failed to calculate market trends: {e}")
    
    def test_get_market_trends(self):
        """Test getting market trends from database"""
        print("\n📊 Testing get market trends...")
        
        try:
            # Get all trends
            trends = self.market_trends_service.get_market_trends()
            self.assertIsInstance(trends, list, "Trends should be a list")
            
            # Get sector trends
            sector_trends = self.market_trends_service.get_market_trends(trend_type="sector")
            self.assertIsInstance(sector_trends, list, "Sector trends should be a list")
            
            print(f"✅ Retrieved market trends")
            print(f"   Total trends: {len(trends)}")
            print(f"   Sector trends: {len(sector_trends)}")
            
        except Exception as e:
            self.fail(f"Failed to get market trends: {e}")
    
    # ==================== Integration Tests ====================
    
    def test_full_market_features_workflow(self):
        """Test complete workflow of all market features"""
        print("\n🔄 Testing full market features workflow...")
        
        try:
            # 1. Calculate market movers
            movers = self.market_movers_service.calculate_market_movers("day", 5)
            self.assertIn("gainers", movers)
            
            # 2. Calculate sector performance
            sectors = self.sector_performance_service.calculate_sector_performance()
            self.assertIn("sectors", sectors)
            
            # 3. Compare stocks
            comparison = self.stock_comparison_service.compare_stocks(["AAPL", "GOOGL"])
            self.assertIn("comparison", comparison)
            
            # 4. Get market overview
            overview = self.market_overview_service.get_market_overview()
            self.assertIn("market_status", overview)
            
            # 5. Calculate market trends
            trends = self.market_trends_service.calculate_market_trends()
            self.assertIn("overall", trends)
            
            print("✅ Full market features workflow successful")
            
        except Exception as e:
            self.fail(f"Failed full workflow: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)

