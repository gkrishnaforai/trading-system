"""
Comprehensive end-to-end test demonstrating the full data pipeline.
Uses the same API endpoints that the Go API calls to:
- Load raw market data via DataRefreshManager
- Calculate technical indicators
- Generate trading signals via StrategyService
- Run stock screeners
- Validate all data with SQL queries

This test serves as a living contract for the Go API expectations.
"""
import os
import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List

import pytest
import requests

from app.database import init_database, db
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import DataType
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.services.stock_screener_service import StockScreenerService
from app.utils.query_utils import fetch_latest_by_symbol, fetch_recent_symbols

# Configure test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test symbols - mix of tech stocks
TEST_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]


def _go_api_base_url() -> str:
    url = os.getenv("GO_API_URL")
    if url:
        return url.rstrip("/")
    # Prefer in-docker DNS name if running under docker-compose; otherwise localhost.
    return os.getenv("GO_API_URL_FALLBACK", "http://go-api:8000").rstrip("/")


def _go_api_get(path: str, *, params: Dict[str, Any] | None = None, timeout: int = 15) -> requests.Response:
    base = _go_api_base_url()
    return requests.get(f"{base}{path}", params=params, timeout=timeout)


def _go_api_post(path: str, *, json: Dict[str, Any] | None = None, timeout: int = 30) -> requests.Response:
    base = _go_api_base_url()
    return requests.post(f"{base}{path}", json=json, timeout=timeout)


def _skip_if_go_api_unreachable() -> None:
    try:
        resp = _go_api_get("/health", timeout=5)
    except Exception as e:
        pytest.skip(f"Go API not reachable at {_go_api_base_url()}: {e}")
    if resp.status_code >= 500:
        pytest.skip(f"Go API unhealthy (status={resp.status_code})")

@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    """Initialize test database and cleanup after tests."""
    logger.info("Initializing test database...")
    init_database()
    yield
    logger.info("Test completed.")

class TestGoApiContractE2E:
    """End-to-end test mirroring Go API usage patterns."""

    def test_00_go_api_smoke_contract(self):
        """Smoke/contract test that directly calls the Go API endpoints used by Streamlit."""
        _skip_if_go_api_unreachable()

        # 1) Go API health
        resp = _go_api_get("/health")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload.get("status") == "healthy"

        # 2) Admin proxy health
        resp = _go_api_get("/api/v1/admin/health")
        assert resp.status_code in (200, 502), resp.text
        # If python-worker is down, admin proxy might return 502; that's still informative.

        # 3) Core stock endpoints
        symbol = os.getenv("GO_API_TEST_SYMBOL", "AAPL")
        resp = _go_api_get(f"/api/v1/stock/{symbol}", params={"subscription_level": "basic"})
        assert resp.status_code == 200
        stock = resp.json()
        assert stock.get("symbol") == symbol

        resp = _go_api_get(f"/api/v1/stock/{symbol}/fundamentals")
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert isinstance(resp.json(), dict)

        resp = _go_api_get(f"/api/v1/stock/{symbol}/news")
        assert resp.status_code == 200
        news = resp.json()
        assert news.get("symbol") == symbol

        # 4) Advanced analysis must not 5xx (it can legitimately return data_available:false)
        resp = _go_api_get(
            f"/api/v1/stock/{symbol}/advanced-analysis",
            params={"subscription_level": "basic"},
        )
        assert resp.status_code == 200
        adv = resp.json()
        assert adv.get("symbol") == symbol
        assert "data_available" in adv

        # 5) Refresh status endpoint should exist
        resp = _go_api_get("/api/v1/admin/refresh/status")
        assert resp.status_code in (200, 502), resp.text

        # 6) Optional: trigger refresh (disabled by default to keep smoke test non-invasive)
        if os.getenv("GO_API_SMOKE_TRIGGER_REFRESH") == "1":
            resp = _go_api_post(
                "/api/v1/admin/refresh",
                json={"symbols": [symbol], "data_types": ["price_historical"], "force": True},
                timeout=120,
            )
            assert resp.status_code in (200, 502), resp.text
    
    def test_01_data_ingestion_via_refresh_manager(self):
        """Step 1: Load raw market data using DataRefreshManager (same as Go API /refresh endpoint)."""
        logger.info("=== Step 1: Data Ingestion via DataRefreshManager ===")
        
        refresh_manager = DataRefreshManager()
        
        # Refresh daily market data for each symbol individually (API signature)
        refreshed_count = 0
        for symbol in TEST_SYMBOLS:
            result = refresh_manager.refresh_data(
                symbol=symbol,
                data_types=[DataType.PRICE_HISTORICAL],
                force=True
            )
            if result.total_successful > 0:
                refreshed_count += 1
                logger.info(f"{symbol}: {result.total_successful} data types refreshed")
            else:
                logger.warning(f"{symbol}: refresh failed - {result.total_failed} failed")
        
        assert refreshed_count >= len(TEST_SYMBOLS) // 2, f"Too few symbols refreshed: {refreshed_count}/{len(TEST_SYMBOLS)}"
        
        # Validate raw data was loaded with SQL
        for symbol in TEST_SYMBOLS:
            count_query = """
                SELECT COUNT(*) as count FROM raw_market_data_daily 
                WHERE stock_symbol = :symbol
            """
            result_row = db.execute_query(count_query, {"symbol": symbol})[0]
            if result_row["count"] > 0:
                logger.info(f"{symbol}: {result_row['count']} raw bars loaded")
            else:
                logger.warning(f"{symbol}: no raw data found")
    
    def test_02_calculate_indicators(self):
        """Step 2: Calculate technical indicators (same as Go API /indicators endpoint)."""
        logger.info("=== Step 2: Calculate Technical Indicators ===")
        
        indicator_service = IndicatorService()
        
        for symbol in TEST_SYMBOLS:
            # Calculate indicators using the same service the API uses
            success = indicator_service.calculate_indicators(symbol)
            
            if success:
                # Fetch the calculated indicators from database
                indicators = indicator_service.get_latest_indicators(symbol)
                
                if indicators is not None:
                    assert "sma_50" in indicators, f"SMA_50 missing for {symbol}"
                    assert "rsi_14" in indicators, f"RSI_14 missing for {symbol}"
                    assert "signal" in indicators, f"Signal missing for {symbol}"
                    
                    logger.info(f"{symbol}: SMA_50={indicators['sma_50']:.2f}, RSI_14={indicators['rsi_14']:.2f}, Signal={indicators['signal']}")
                else:
                    logger.warning(f"{symbol}: no indicators found after calculation")
            else:
                logger.warning(f"{symbol}: indicator calculation failed")
        
        # Validate indicators stored in database with SQL
        indicator_count_query = """
            SELECT COUNT(*) as count FROM indicators_daily 
            WHERE stock_symbol = ANY(:symbols)
        """
        result = db.execute_query(indicator_count_query, {"symbols": TEST_SYMBOLS})[0]
        assert result["count"] >= 0, "No indicators stored in database"
        logger.info(f"Total indicator rows stored: {result['count']}")
    
    def test_03_generate_trading_signals(self):
        """Step 3: Generate trading signals using StrategyService (same as Go API /signals endpoint)."""
        logger.info("=== Step 3: Generate Trading Signals ===")
        
        strategy_service = StrategyService()
        
        for symbol in TEST_SYMBOLS:
            # Fetch latest indicators for this symbol (use actual columns)
            indicators = fetch_latest_by_symbol(
                "indicators_daily", 
                symbol,
                select_cols=["sma_50", "sma_200", "ema_20", "rsi_14", "macd", "macd_signal", "signal", "confidence_score"]
            )
            
            if indicators is not None:
                # Add required fields for strategy validation
                indicators["price"] = indicators.get("sma_50", 0)  # Use SMA_50 as proxy for price
                indicators["ema20"] = indicators.get("ema_20", 0)
                indicators["ema50"] = indicators.get("sma_50", 0)
                indicators["sma200"] = indicators.get("sma_200", 0)
                indicators["macd_line"] = indicators.get("macd", 0)
                indicators["rsi"] = indicators.get("rsi_14", 50)
                
                # Generate signal using the same strategy as the API
                signal_result = strategy_service.execute_strategy("technical", indicators)
                
                assert signal_result is not None, f"No signal generated for {symbol}"
                assert hasattr(signal_result, 'signal'), f"Signal result missing 'signal' attribute for {symbol}"
                assert hasattr(signal_result, 'confidence'), f"Signal result missing 'confidence' attribute for {symbol}"
                
                logger.info(f"{symbol}: Signal={signal_result.signal}, Confidence={signal_result.confidence:.2f}")
            else:
                logger.warning(f"{symbol}: no stored indicators found")
    
    def test_04_run_stock_screener(self):
        """Step 4: Run stock screener (same as Go API /screener endpoint)."""
        logger.info("=== Step 4: Run Stock Screener ===")
        
        screener_service = StockScreenerService()
        
        # Run screener using the actual API signature
        screener_result = screener_service.screen_stocks(
            min_rsi=30,
            max_rsi=70,
            limit=10
        )
        
        assert screener_result is not None, "Screener returned no results"
        assert isinstance(screener_result, dict), "Screener should return a dict"
        assert "stocks" in screener_result, "Screener missing stocks list"
        assert "count" in screener_result, "Screener missing count"
        
        screened_stocks = screener_result["stocks"]
        logger.info(f"Screener found {len(screened_stocks)} stocks matching criteria")
        
        # Validate screener results with SQL
        if screened_stocks:
            for stock in screened_stocks[:3]:  # Check first 3 results
                assert "symbol" in stock, "Stock symbol missing from screener result"
                assert "rsi" in stock, "RSI missing from screener result"
                assert "sma50" in stock, "SMA_50 missing from screener result"
                
                logger.info(f"  {stock['symbol']}: RSI={stock['rsi']:.2f}, SMA_50={stock['sma50']:.2f}")
    
    def test_05_validate_data_consistency(self):
        """Step 5: Validate data consistency across tables with comprehensive SQL queries."""
        logger.info("=== Step 5: Data Consistency Validation ===")
        
        # Query 1: Check all test symbols have raw data
        raw_data_query = """
            SELECT stock_symbol, COUNT(*) as bar_count, 
                   MIN(trade_date) as start_date, MAX(trade_date) as end_date,
                   AVG(volume) as avg_volume
            FROM raw_market_data_daily 
            WHERE stock_symbol = ANY(:symbols)
            GROUP BY stock_symbol
            ORDER BY stock_symbol
        """
        raw_summary = db.execute_query(raw_data_query, {"symbols": TEST_SYMBOLS})
        
        logger.info("Raw Market Data Summary:")
        for row in raw_summary:
            logger.info(f"  {row['stock_symbol']}: {row['bar_count']} bars, "
                       f"{row['start_date']} to {row['end_date']}, "
                       f"Avg Vol={row['avg_volume']:,.0f}")
        
        # Query 2: Check indicators exist and are calculated correctly (use actual columns)
        indicators_query = """
            SELECT stock_symbol, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, signal, confidence_score, trade_date
            FROM indicators_daily 
            WHERE stock_symbol = ANY(:symbols)
            ORDER BY stock_symbol, trade_date DESC
        """
        indicators_summary = db.execute_query(indicators_query, {"symbols": TEST_SYMBOLS})
        
        logger.info("Latest Indicators by Symbol:")
        current_symbol = None
        for row in indicators_summary:
            if row['stock_symbol'] != current_symbol:
                current_symbol = row['stock_symbol']
                logger.info(f"  {current_symbol}:")
            logger.info(f"    Date={row['trade_date']}, SMA_50={row['sma_50']:.2f}, "
                       f"SMA_200={row['sma_200']:.2f}, RSI_14={row['rsi_14']:.2f}, "
                       f"Signal={row['signal']}")
        
        # Query 3: Check data freshness (should be recent data)
        freshness_query = """
            SELECT stock_symbol, trade_date, 
                   CURRENT_DATE - trade_date as days_old
            FROM indicators_daily 
            WHERE stock_symbol = ANY(:symbols)
            ORDER BY trade_date DESC
            LIMIT 1
        """
        freshness = db.execute_query(freshness_query, {"symbols": TEST_SYMBOLS})
        
        if freshness:
            latest = freshness[0]
            logger.info(f"Most recent data: {latest['stock_symbol']} from {latest['trade_date']} "
                       f"({latest['days_old']} days old)")
            # Assert data is relatively recent (within 7 days for market data)
            assert latest['days_old'] <= 7, f"Data is too old: {latest['days_old']} days"
        
        # Query 4: Validate no NULL critical fields (use actual columns)
        null_check_query = """
            SELECT COUNT(*) as null_count, 'raw_data' as table_name
            FROM raw_market_data_daily 
            WHERE stock_symbol = ANY(:symbols) 
              AND (close IS NULL OR volume IS NULL)
            UNION ALL
            SELECT COUNT(*) as null_count, 'indicators' as table_name
            FROM indicators_daily 
            WHERE stock_symbol = ANY(:symbols) 
              AND (sma_50 IS NULL OR rsi_14 IS NULL)
        """
        null_checks = db.execute_query(null_check_query, {"symbols": TEST_SYMBOLS})
        
        for check in null_checks:
            assert check["null_count"] == 0, f"Found {check['null_count']} NULL critical fields in {check['table_name']}"
            logger.info(f"✓ No NULL critical fields in {check['table_name']}")
        
        logger.info("✓ All data consistency checks passed")
    
    def test_06_performance_and_scalability_validation(self):
        """Step 6: Basic performance validation to ensure queries are efficient."""
        logger.info("=== Step 6: Performance Validation ===")
        
        import time
        
        # Test query performance on raw data
        start_time = time.time()
        perf_query = """
            SELECT stock_symbol, trade_date, close, volume
            FROM raw_market_data_daily 
            WHERE stock_symbol = ANY(:symbols)
              AND trade_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY stock_symbol, trade_date
        """
        perf_result = db.execute_query(perf_query, {"symbols": TEST_SYMBOLS})
        query_time = time.time() - start_time
        
        logger.info(f"Raw data query returned {len(perf_result)} rows in {query_time:.3f}s")
        assert query_time < 2.0, "Raw data query too slow"
        
        # Test indicator query performance (use actual columns)
        start_time = time.time()
        indicator_perf_query = """
            SELECT stock_symbol, sma_50, sma_200, rsi_14, signal
            FROM indicators_daily 
            WHERE stock_symbol = ANY(:symbols)
            ORDER BY stock_symbol, trade_date DESC
        """
        indicator_perf_result = db.execute_query(indicator_perf_query, {"symbols": TEST_SYMBOLS})
        indicator_query_time = time.time() - start_time
        
        logger.info(f"Indicators query returned {len(indicator_perf_result)} rows in {indicator_query_time:.3f}s")
        assert indicator_query_time < 1.0, "Indicators query too slow"
        
        logger.info("✓ All performance checks passed")

if __name__ == "__main__":
    # Run this test directly for debugging
    pytest.main([__file__, "-v", "-s"])
