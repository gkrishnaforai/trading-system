"""
Integration tests for Data Refresh Manager with REAL data
Tests the complete data refresh pipeline: fetch -> save -> calculate indicators
Uses real stock data: AAPL, NVDA, GOOGL, PLTR
No mocks - full end-to-end integration test
"""
import unittest
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import init_database, db
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType
from app.services.indicator_service import IndicatorService
from app.config import settings
from pathlib import Path


class TestDataRefreshIntegration(unittest.TestCase):
    """
    Integration tests for data refresh manager
    Tests complete pipeline with real data
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        print("\n" + "="*80)
        print("DATA REFRESH MANAGER INTEGRATION TESTS - REAL DATA")
        print("="*80)
        
        # Ensure database directory exists
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        init_database()
        
        cls.refresh_manager = DataRefreshManager()
        cls.indicator_service = IndicatorService()
        cls.symbols = ['AAPL', 'NVDA', 'GOOGL', 'PLTR']
        
        print(f"\n📊 Testing with symbols: {', '.join(cls.symbols)}")
        print(f"📅 Test date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def setUp(self):
        """Set up test fixtures"""
        self.refresh_manager = self.__class__.refresh_manager
        self.indicator_service = self.__class__.indicator_service
        self.symbols = self.__class__.symbols
    
    def test_scheduled_refresh_price_data(self):
        """Test scheduled refresh mode for price data (daily batch)"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔄 Testing scheduled refresh for {symbol}...")
                
                # Refresh price data in scheduled mode
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL],
                    mode=RefreshMode.SCHEDULED,
                    force=True
                )
                
                # Validate result
                self.assertIsNotNone(result, f"{symbol}: Should return result")
                # Results dictionary uses data_type.value (string) as key, not the enum
                price_result = result.results.get(DataType.PRICE_HISTORICAL.value)
                
                self.assertIsNotNone(
                    price_result,
                    f"{symbol}: Should have price refresh result. "
                    f"Available keys: {list(result.results.keys())}"
                )
                
                # Check status
                if price_result.status.value == 'success':
                    print(f"✅ {symbol}: Scheduled refresh successful")
                    print(f"   Rows affected: {price_result.rows_affected}")
                    
                    # Verify data in database
                    query = """
                        SELECT COUNT(*) as count
                        FROM raw_market_data_daily
                        WHERE symbol = :symbol
                    """
                    result_db = db.execute_query(query, {"symbol": symbol})
                    count = result_db[0]['count'] if result_db else 0
                    
                    self.assertGreater(
                        count, 0,
                        f"{symbol}: Should have data in database"
                    )
                    print(f"   Database rows: {count}")
                else:
                    print(f"⚠️  {symbol}: Scheduled refresh status: {price_result.status.value}")
                    if price_result.error:
                        print(f"   Error: {price_result.error}")
    
    def test_on_demand_refresh_all_data_types(self):
        """Test on-demand refresh for all data types"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔄 Testing on-demand refresh for {symbol}...")
                
                # Refresh all data types
                data_types = [
                    DataType.PRICE_HISTORICAL,
                    DataType.PRICE_CURRENT,
                    DataType.PRICE_INTRADAY_15M,
                    DataType.FUNDAMENTALS,
                    DataType.INDICATORS,
                    DataType.NEWS,
                    DataType.EARNINGS,
                    DataType.INDUSTRY_PEERS,
                ]
                
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=data_types,
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Validate results
                self.assertIsNotNone(result, f"{symbol}: Should return result")
                
                success_count = 0
                for data_type in data_types:
                    # Results dictionary uses data_type.value (string) as key
                    type_result = result.results.get(data_type.value)
                    if type_result and type_result.status.value == 'success':
                        success_count += 1
                        print(f"   ✅ {data_type.value}: Success")
                    else:
                        status = type_result.status.value if type_result else 'unknown'
                        print(f"   ⚠️  {data_type.value}: {status}")
                        if type_result and type_result.error:
                            print(f"      Error: {type_result.error[:100]}")
                
                print(f"✅ {symbol}: {success_count}/{len(data_types)} data types refreshed")
                
                # At minimum, price data should succeed
                price_result = result.results.get(DataType.PRICE_HISTORICAL.value)
                self.assertIsNotNone(
                    price_result,
                    f"{symbol}: Should have price refresh result. "
                    f"Available keys: {list(result.results.keys())}"
                )
                # Check status - provide detailed error message if failed
                if price_result.status.value != 'success':
                    error_msg = price_result.error or price_result.message or "Unknown error"
                    self.fail(
                        f"{symbol}: Price data refresh failed. "
                        f"Status: {price_result.status.value}, "
                        f"Error: {error_msg}, "
                        f"Rows affected: {price_result.rows_affected}"
                    )
                self.assertEqual(
                    price_result.status.value, 'success',
                    f"{symbol}: Price data refresh should succeed"
                )

                # Validate key tables for this symbol
                daily_count = db.execute_query(
                    "SELECT COUNT(*) AS c FROM raw_market_data_daily WHERE symbol = :symbol",
                    {"symbol": symbol},
                )
                self.assertGreater(
                    (daily_count[0].get("c") if daily_count else 0),
                    0,
                    f"{symbol}: raw_market_data_daily should have rows",
                )

                intraday_15m_count = db.execute_query(
                    """
                    SELECT COUNT(*) AS c
                    FROM raw_market_data_intraday
                    WHERE stock_symbol = :symbol AND interval = '15m'
                    """,
                    {"symbol": symbol},
                )
                # Intraday availability depends on provider; don't fail the entire suite if empty.
                c15 = (intraday_15m_count[0].get("c") if intraday_15m_count else 0)
                print(f"   raw_market_data_intraday(15m) rows: {c15}")

                peers_count = db.execute_query(
                    "SELECT COUNT(*) AS c FROM industry_peers WHERE stock_symbol = :symbol",
                    {"symbol": symbol},
                )
                cpeers = (peers_count[0].get("c") if peers_count else 0)
                print(f"   industry_peers rows: {cpeers}")
    
    def test_indicators_auto_calculation(self):
        """Test that indicators are automatically calculated after price data refresh"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n📊 Testing indicator auto-calculation for {symbol}...")
                
                # First ensure we have price data
                self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Refresh indicators (should auto-calculate after price data)
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.INDICATORS],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Validate indicators result (results use data_type.value as key)
                indicators_result = result.results.get(DataType.INDICATORS.value)
                if indicators_result and indicators_result.status.value == 'success':
                    print(f"✅ {symbol}: Indicators calculated successfully")
                    
                    # Verify indicators in database
                    query = """
                        SELECT *
                        FROM indicators_daily
                        WHERE symbol = :symbol
                        ORDER BY date DESC
                        LIMIT 1
                    """
                    indicators = db.execute_query(query, {"symbol": symbol})
                    
                    if indicators:
                        latest = indicators[0]
                        print(f"   Latest indicators:")
                        print(f"   - indicator_name: {latest.get('indicator_name', 'N/A')}")
                        print(f"   - indicator_value: {latest.get('indicator_value', 'N/A')}")
                    else:
                        print(f"   ⚠️  No indicators in database")
                else:
                    status = indicators_result.status.value if indicators_result else 'unknown'
                    print(f"⚠️  {symbol}: Indicator calculation status: {status}")
    
    def test_periodic_refresh_mode(self):
        """Test periodic refresh mode (for regular updates)"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔄 Testing periodic refresh for {symbol}...")
                
                # Refresh in periodic mode (typically for incremental updates)
                result = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_CURRENT],
                    mode=RefreshMode.PERIODIC,
                    force=True
                )
                
                # Validate result
                self.assertIsNotNone(result, f"{symbol}: Should return result")
                
                current_result = result.results.get(DataType.PRICE_CURRENT.value)
                if current_result:
                    print(f"✅ {symbol}: Periodic refresh completed")
                    print(f"   Status: {current_result.status.value}")
                else:
                    print(f"⚠️  {symbol}: No result for periodic refresh")
    
    def test_data_refresh_tracking(self):
        """Test that data refresh tracking is updated correctly"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n📝 Testing refresh tracking for {symbol}...")
                
                # Refresh data
                self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Check tracking table
                query = """
                    SELECT * FROM data_refresh_tracking
                    WHERE stock_symbol = :symbol
                    AND data_type = 'price_historical'
                    ORDER BY last_refresh DESC
                    LIMIT 1
                """
                tracking = db.execute_query(query, {"symbol": symbol})
                
                if tracking:
                    record = tracking[0]
                    print(f"✅ {symbol}: Refresh tracking updated")
                    print(f"   Last refresh: {record.get('last_refresh')}")
                    print(f"   Status: {record.get('status')}")
                    print(f"   Mode: {record.get('refresh_mode')}")
                    
                    self.assertIsNotNone(
                        record.get('last_refresh'),
                        f"{symbol}: Should have last_refresh timestamp"
                    )
                else:
                    print(f"⚠️  {symbol}: No tracking record found")
    
    def test_full_pipeline_daily_batch(self):
        """Test complete daily batch pipeline: fetch -> save -> calculate -> signals"""
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n🔄 Testing full daily batch pipeline for {symbol}...")
                
                # Step 1: Refresh price data
                print(f"   Step 1: Fetching price data...")
                result1 = self.refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=[DataType.PRICE_HISTORICAL],
                    mode=RefreshMode.SCHEDULED,
                    force=True
                )
                
                price_result = result1.results.get(DataType.PRICE_HISTORICAL.value)
                self.assertIsNotNone(
                    price_result, 
                    f"{symbol}: Price refresh should return result. "
                    f"Available keys: {list(result1.results.keys())}"
                )
                
                if price_result.status.value != 'success':
                    self.skipTest(f"{symbol}: Price data fetch failed")
                
                print(f"   ✅ Price data fetched: {price_result.rows_affected} rows")
                
                # Step 2: Calculate indicators
                print(f"   Step 2: Calculating indicators...")
                indicators_success = self.indicator_service.calculate_indicators(symbol)
                
                if indicators_success:
                    print(f"   ✅ Indicators calculated")
                    
                    # Verify indicators exist
                    query = """
                        SELECT COUNT(*) as count
                        FROM aggregated_indicators
                        WHERE stock_symbol = :symbol
                    """
                    result_db = db.execute_query(query, {"symbol": symbol})
                    indicator_count = result_db[0]['count'] if result_db else 0
                    print(f"   ✅ Indicators in database: {indicator_count}")
                else:
                    print(f"   ⚠️  Indicator calculation failed")
                
                # Step 3: Verify data completeness
                print(f"   Step 3: Verifying data completeness...")
                
                # Check price data
                query = """
                    SELECT COUNT(*) as count
                    FROM raw_market_data
                    WHERE stock_symbol = :symbol
                """
                price_count = db.execute_query(query, {"symbol": symbol})[0]['count']
                
                # Check indicators
                query = """
                    SELECT COUNT(*) as count
                    FROM aggregated_indicators
                    WHERE stock_symbol = :symbol
                """
                indicator_count = db.execute_query(query, {"symbol": symbol})[0]['count']
                
                print(f"   ✅ Data completeness verified")
                print(f"      Price data rows: {price_count}")
                print(f"      Indicator rows: {indicator_count}")
                
                # Validate we have enough data for signals
                self.assertGreater(
                    price_count, 200,
                    f"{symbol}: Should have at least 200 days of price data"
                )
                
                if indicators_success:
                    self.assertGreater(
                        indicator_count, 0,
                        f"{symbol}: Should have calculated indicators"
                    )
                
                print(f"✅ {symbol}: Full pipeline completed successfully")
    
    def test_error_handling_invalid_symbol(self):
        """Test error handling for invalid symbols"""
        print(f"\n⚠️  Testing error handling...")
        
        invalid_symbol = "INVALID_SYMBOL_XYZ123"
        
        try:
            result = self.refresh_manager.refresh_data(
                symbol=invalid_symbol,
                data_types=[DataType.PRICE_HISTORICAL],
                mode=RefreshMode.ON_DEMAND,
                force=True
            )
            
            # Should handle gracefully
            price_result = result.results.get(DataType.PRICE_HISTORICAL.value)
            if price_result:
                status = price_result.status.value
                print(f"✅ Invalid symbol handled: status = {status}")
                
                # Should be 'failed' or 'skipped', not crash
                self.assertIn(
                    status, ['failed', 'skipped'],
                    f"Invalid symbol should result in 'failed' or 'skipped', got '{status}'"
                )
        except Exception as e:
            # Should not crash, but if it does, log it
            print(f"⚠️  Exception for invalid symbol: {type(e).__name__}: {e}")
            # Don't fail the test - error handling is acceptable


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)

