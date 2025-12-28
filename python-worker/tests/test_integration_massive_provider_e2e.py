"""
End-to-end integration test for Massive.com provider with real Postgres ingestion.
Brings up containers, calls Massive API, loads data via DataRefreshManager,
and asserts rows exist in the new schema tables.
"""
import unittest
import sys
import os
import time
from datetime import datetime, date
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.data_sources.massive_source import MassiveSource
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import DataType
from app.database import db
from app.repositories.market_data_daily_repository import MarketDataDailyRepository
from app.repositories.indicators_repository import IndicatorsRepository
from app.repositories.market_data_intraday_repository import MarketDataIntradayRepository
from app.config import settings


class TestMassiveProviderE2E(unittest.TestCase):
    """End-to-end integration test for Massive.com provider with Postgres."""

    @classmethod
    def setUpClass(cls):
        """Initialize Massive client and ensure DB is reachable."""
        print("\n" + "="*80)
        print("MASSIVE.COM END-TO-END INTEGRATION TEST (REAL API + POSTGRES)")
        print("="*80)
        
        # Show configuration values before checking
        print(f"🔧 Configuration check:")
        print(f"   - massive_enabled: {settings.massive_enabled}")
        print(f"   - massive_api_key: {'SET' if settings.massive_api_key else 'NOT SET'}")
        print(f"   - database_url: {settings.database_url}")
        
        # Check if running locally and suggest fix
        if "postgres:" in settings.database_url and not os.path.exists("/.dockerenv"):
            print("⚠️  LOCAL DETECTION: Running outside Docker but DATABASE_URL uses 'postgres' hostname")
            print("   For local testing, either:")
            print("   1. Create python-worker/.env with DATABASE_URL=postgresql://trading:trading-dev@localhost:5432/trading?sslmode=disable")
            print("   2. Or run tests inside Docker: docker-compose exec python-worker python -m pytest tests/test_integration_massive_provider_e2e.py -v -s")
        print("="*80)

        if not settings.massive_enabled:
            print("❌ SKIP: Massive.com not enabled. Set MASSIVE_ENABLED=true in .env")
            raise unittest.SkipTest("Massive.com not enabled. Set MASSIVE_ENABLED=true.")
        if not settings.massive_api_key:
            print("❌ SKIP: Massive.com API key not configured. Set MASSIVE_API_KEY in .env")
            raise unittest.SkipTest("Massive.com API key not configured.")

        # Initialize Massive source
        cls.source = MassiveSource()
        print(f"✅ Massive client initialized (rate limit: {settings.massive_rate_limit_calls}/{settings.massive_rate_limit_window}s)")

        # Initialize DataRefreshManager
        cls.refresh_manager = DataRefreshManager()
        print("✅ DataRefreshManager initialized")

        # Initialize database connection
        db.initialize()
        print(f"✅ Database initialized: {db.engine.url}")

        # Verify DB connectivity
        try:
            result = db.execute_query("SELECT 1 as test")
            assert result and result[0]["test"] == 1
            print(f"✅ Database reachable: {db.engine.url}")
        except Exception as e:
            raise unittest.SkipTest(f"Database not reachable: {e}")

        # Test symbols
        cls.symbols = ["AAPL", "MSFT", "NVDA"]
        print(f"📊 Test symbols: {', '.join(cls.symbols)}")
        print("="*80 + "\n")

    def setUp(self):
        """Clean up any existing data for the test symbols to ensure idempotency."""
        for symbol in self.symbols:
            # Clean new tables
            db.execute_update("DELETE FROM raw_market_data_daily WHERE stock_symbol = :symbol", {"symbol": symbol})
            db.execute_update("DELETE FROM indicators_daily WHERE stock_symbol = :symbol", {"symbol": symbol})
            db.execute_update("DELETE FROM fundamentals_snapshots WHERE stock_symbol = :symbol", {"symbol": symbol})
            db.execute_update("DELETE FROM industry_peers WHERE stock_symbol = :symbol", {"symbol": symbol})
            db.execute_update("DELETE FROM data_ingestion_state WHERE stock_symbol = :symbol", {"symbol": symbol})

    def test_full_data_load_pipeline(self):
        """Run full pipeline: fetch -> save via DataRefreshManager -> verify DB rows."""
        print("\n🚀 Running full data load pipeline...")
        for symbol in self.symbols:
            with self.subTest(symbol=symbol):
                print(f"\n--- {symbol} ---")
                # 1) Load via DataRefreshManager (price_historical + fundamentals + indicators + industry_peers)
                self.refresh_manager.refresh_data(symbol, data_types=[DataType.PRICE_HISTORICAL, DataType.FUNDAMENTALS, DataType.INDICATORS, DataType.INDUSTRY_PEERS])

                # 2) Verify raw_market_data_daily rows
                rows = db.execute_query("SELECT COUNT(*) as cnt FROM raw_market_data_daily WHERE stock_symbol = :symbol", {"symbol": symbol})
                count = rows[0]["cnt"]
                self.assertGreater(count, 200, f"{symbol}: Expected >200 daily rows, got {count}")
                print(f"✅ raw_market_data_daily: {count} rows")

                # 3) Verify indicators_daily rows
                rows = db.execute_query("SELECT COUNT(*) as cnt FROM indicators_daily WHERE stock_symbol = :symbol", {"symbol": symbol})
                count = rows[0]["cnt"]
                self.assertGreater(count, 200, f"{symbol}: Expected >200 indicator rows, got {count}")
                print(f"✅ indicators_daily: {count} rows")

                # 4) Verify fundamentals_snapshots (at least one)
                rows = db.execute_query("SELECT COUNT(*) as cnt FROM fundamentals_snapshots WHERE stock_symbol = :symbol", {"symbol": symbol})
                count = rows[0]["cnt"]
                self.assertGreaterEqual(count, 1, f"{symbol}: Expected >=1 fundamentals row, got {count}")
                print(f"✅ fundamentals_snapshots: {count} rows")

                # 5) Verify industry_peers (optional)
                rows = db.execute_query("SELECT COUNT(*) as cnt FROM industry_peers WHERE stock_symbol = :symbol", {"symbol": symbol})
                count = rows[0]["cnt"]
                print(f"✅ industry_peers: {count} rows (may be 0)")

                # 6) Verify data_ingestion_state entries
                rows = db.execute_query("SELECT COUNT(*) as cnt FROM data_ingestion_state WHERE stock_symbol = :symbol", {"symbol": symbol})
                count = rows[0]["cnt"]
                self.assertGreater(count, 0, f"{symbol}: Expected >=1 ingestion state rows, got {count}")
                print(f"✅ data_ingestion_state: {count} rows")

    def test_massive_api_endpoints(self):
        """Direct Massive API calls to validate all endpoints."""
        print("\n🔌 Testing Massive API endpoints directly...")
        symbol = "AAPL"
        # Price data
        df = self.source.fetch_price_data(symbol, period="1mo")
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty)
        self.assertGreater(len(df), 15)
        print(f"✅ fetch_price_data: {len(df)} rows (1mo)")

        # Current price (may not be available on all plans)
        price = self.source.fetch_current_price(symbol)
        if price is not None:
            self.assertIsInstance(price, (int, float))
            self.assertGreater(price, 0)
            print(f"✅ fetch_current_price: ${price:.2f}")
        else:
            print("⚠️  fetch_current_price: Not available on current plan (skipped)")

        # Fundamentals
        fund = self.source.fetch_fundamentals(symbol)
        self.assertIsInstance(fund, dict)
        if fund:
            print(f"✅ fetch_fundamentals: {len(fund)} fields")
        else:
            print("⚠️ fetch_fundamentals: empty (may be normal)")

        # News
        news = self.source.fetch_news(symbol, limit=5)
        self.assertIsInstance(news, list)
        print(f"✅ fetch_news: {len(news)} articles")

        # Earnings
        earnings = self.source.fetch_earnings(symbol)
        self.assertIsInstance(earnings, list)
        print(f"✅ fetch_earnings: {len(earnings)} records")

        # Industry peers
        peers = self.source.fetch_industry_peers(symbol)
        self.assertIsInstance(peers, dict)
        print(f"✅ fetch_industry_peers: sector={peers.get('sector')}, peers={len(peers.get('peers', []))}")

    def test_idempotent_upserts(self):
        """Run refresh twice; ensure no duplicate rows (idempotency via ON CONFLICT)."""
        symbol = "MSFT"
        print(f"\n🔁 Testing idempotency for {symbol}...")

        # First refresh
        self.refresh_manager.refresh_data(symbol, data_types=["price_historical"])
        rows1 = db.execute_query("SELECT COUNT(*) as cnt FROM raw_market_data_daily WHERE stock_symbol = :symbol", {"symbol": symbol})[0]["cnt"]
        print(f"First refresh: {rows1} rows")

        # Second refresh (should not increase row count)
        self.refresh_manager.refresh_data(symbol, data_types=["price_historical"])
        rows2 = db.execute_query("SELECT COUNT(*) as cnt FROM raw_market_data_daily WHERE stock_symbol = :symbol", {"symbol": symbol})[0]["cnt"]
        print(f"Second refresh: {rows2} rows")
        self.assertEqual(rows1, rows2, "Idempotency failed: row count changed on second refresh")
        print("✅ Idempotency verified")

    def test_coverage_of_all_data_load_options(self):
        """Ensure all data load paths from Massive are exercised."""
        print("\n🧪 Testing all data load options...")
        symbol = "NVDA"
        # Load all supported data types
        self.refresh_manager.refresh_data(symbol, data_types=["price_historical", "fundamentals", "indicators", "industry_peers", "earnings"])
        # Spot-check each table
        for table in ["raw_market_data_daily", "indicators_daily", "fundamentals_snapshots", "industry_peers", "data_ingestion_state"]:
            rows = db.execute_query(f"SELECT COUNT(*) as cnt FROM {table} WHERE stock_symbol = :symbol", {"symbol": symbol})
            print(f"✅ {table}: {rows[0]['cnt']} rows")

if __name__ == "__main__":
    unittest.main(verbosity=2)
