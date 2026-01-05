#!/usr/bin/env python3
"""
Test SQL queries against the new normalized schema.
No mocks - uses real database to catch syntax errors.
"""

import unittest
import os
import sys
from datetime import date

# Add project root
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database, db
from app.repositories.market_data_daily_repository import MarketDataDailyRepository
from app.repositories.base_repository import BaseRepository

class TestNormalizedSchemaSQL(unittest.TestCase):
    """Test SQL queries work with normalized schema"""
    
    @classmethod
    def setUpClass(cls):
        """Initialize database connection"""
        init_database()
        
    def test_fetch_market_data_sql(self):
        """Test the market data fetch query works with new schema"""
        print("\n🧪 Testing market data fetch SQL...")
        
        # Test the exact query from fetch_by_symbol
        query = """
            SELECT m.date as date,
                   m.open_price as open,
                   m.high_price as high,
                   m.low_price as low,
                   m.close_price as close,
                   m.adj_close_price as adj_close,
                   m.volume as volume
            FROM stock_market_metrics m
            JOIN stocks s ON s.id = m.stock_id
            WHERE s.symbol = :symbol
            ORDER BY date ASC
        """
        
        try:
            result = db.execute_query(query, {"symbol": "AAPL"})
            print(f"✅ Market data query succeeded: {len(result)} rows")
        except Exception as e:
            self.fail(f"Market data query failed: {e}")
            
    def test_fetch_indicators_sql(self):
        """Test the technical indicators fetch query works"""
        print("\n🧪 Testing technical indicators fetch SQL...")
        
        query = """
            SELECT i.date as date,
                   i.sma_20, i.sma_50, i.sma_200,
                   i.ema_12, i.ema_26,
                   i.rsi_14,
                   i.macd, i.macd_signal, i.macd_histogram,
                   i.bollinger_upper, i.bollinger_middle, i.bollinger_lower,
                   i.stoch_k, i.stoch_d,
                   i.atr_14, i.adx, i.cci, i.roc, i.williams_r
            FROM stock_technical_indicators i
            JOIN stocks s ON s.id = i.stock_id
            WHERE s.symbol = :symbol
            ORDER BY date ASC
        """
        
        try:
            result = db.execute_query(query, {"symbol": "AAPL"})
            print(f"✅ Indicators query succeeded: {len(result)} rows")
        except Exception as e:
            self.fail(f"Indicators query failed: {e}")
            
    def test_upsert_market_data_sql(self):
        """Test upsert works with new OHLCV columns"""
        print("\n🧪 Testing market data upsert SQL...")
        
        # Ensure TEST stock exists
        db.execute_update("""
            INSERT INTO stocks (symbol, company_name, exchange) 
            VALUES ('TEST', 'Test Stock', 'NASDAQ')
            ON CONFLICT (symbol) DO NOTHING
        """)
        
        # Get stock_id
        stock_result = db.execute_query(
            "SELECT id FROM stocks WHERE symbol = :symbol",
            {"symbol": "TEST"}
        )
        if not stock_result:
            self.skipTest("Could not create test stock")
            
        stock_id = stock_result[0]["id"]
        
        # Test upsert with all OHLCV fields
        upsert_rows = [{
            "stock_id": stock_id,
            "date": date.today(),
            "open_price": 100.0,
            "high_price": 105.0,
            "low_price": 95.0,
            "close_price": 102.0,
            "adj_close_price": 101.5,
            "volume": 1000000,
            "source": "test"
        }]
        
        try:
            count = BaseRepository.upsert_many(
                table="stock_market_metrics",
                unique_columns=["stock_id", "date", "source"],
                rows=upsert_rows
            )
            self.assertEqual(count, 1)
            print("✅ Market data upsert succeeded")
        except Exception as e:
            self.fail(f"Market data upsert failed: {e}")
            
    def test_upsert_indicators_sql(self):
        """Test technical indicators upsert works"""
        print("\n🧪 Testing indicators upsert SQL...")
        
        # Get test stock_id
        stock_result = db.execute_query(
            "SELECT id FROM stocks WHERE symbol = :symbol",
            {"symbol": "TEST"}
        )
        if not stock_result:
            self.skipTest("Test stock not found")
            
        stock_id = stock_result[0]["id"]
        
        # Test indicators upsert
        upsert_rows = [{
            "stock_id": stock_id,
            "date": date.today(),
            "sma_20": 101.0,
            "sma_50": 100.5,
            "sma_200": 99.0,
            "ema_12": 101.5,
            "ema_26": 100.8,
            "rsi_14": 55.0,
            "macd": 0.5,
            "macd_signal": 0.3,
            "macd_histogram": 0.2,
            "bollinger_upper": 105.0,
            "bollinger_middle": 100.0,
            "bollinger_lower": 95.0,
            "stoch_k": 60.0,
            "stoch_d": 55.0,
            "atr_14": 2.5,
            "adx": 25.0,
            "cci": 100.0,
            "roc": 1.5,
            "williams_r": -30.0,
            "source": "test"
        }]
        
        try:
            count = BaseRepository.upsert_many(
                table="stock_technical_indicators",
                unique_columns=["stock_id", "date", "source"],
                rows=upsert_rows
            )
            self.assertEqual(count, 1)
            print("✅ Indicators upsert succeeded")
        except Exception as e:
            self.fail(f"Indicators upsert failed: {e}")
            
    def test_screener_query_sql(self):
        """Test the screener query works with normalized schema"""
        print("\n🧪 Testing screener SQL...")
        
        query = """
            WITH latest_metrics AS (
                SELECT DISTINCT ON (s.id)
                    s.symbol AS stock_symbol,
                    sm.date AS trade_date,
                    sm.open_price,
                    sm.high_price,
                    sm.low_price,
                    sm.close_price AS current_price,
                    sm.volume,
                    s.market_cap,
                    s.sector,
                    s.industry
                FROM stocks s
                LEFT JOIN stock_market_metrics sm
                    ON sm.stock_id = s.id
                WHERE s.symbol = ANY(:symbols)
                ORDER BY s.id, sm.date DESC
            ),
            latest_indicators AS (
                SELECT DISTINCT ON (i.stock_id)
                    i.stock_id,
                    i.sma_50,
                    i.sma_200,
                    i.rsi_14
                FROM stock_technical_indicators i
                ORDER BY i.stock_id, i.date DESC
            )
            SELECT
                m.stock_symbol,
                m.trade_date as date,
                m.current_price,
                COALESCE(i.sma_50, NULL) as sma50,
                COALESCE(i.sma_200, NULL) as sma200,
                COALESCE(i.rsi_14, NULL) as rsi,
                NULL as signal,
                NULL as confidence_score,
                'bullish' as long_term_trend,
                'bullish' as medium_term_trend,
                0 as fundamental_score,
                false as has_good_fundamentals,
                false as is_growth_stock,
                COALESCE(m.current_price < i.sma_50, false) as price_below_sma50,
                COALESCE(m.current_price < i.sma_200, false) as price_below_sma200,
                m.market_cap,
                NULL as pe_ratio
            FROM latest_metrics m
            LEFT JOIN latest_indicators i ON i.stock_id = (
                SELECT id FROM stocks s2 WHERE s2.symbol = m.stock_symbol
            )
            WHERE 1=1
            AND rsi_14 <= :max_rsi
            ORDER BY stock_symbol ASC
            LIMIT :limit
        """
        
        try:
            result = db.execute_query(query, {
                "symbols": ["AAPL", "MSFT"],
                "max_rsi": 35.0,
                "limit": 10
            })
            print(f"✅ Screener query succeeded: {len(result)} rows")
        except Exception as e:
            self.fail(f"Screener query failed: {e}")

if __name__ == "__main__":
    unittest.main(verbosity=2)
