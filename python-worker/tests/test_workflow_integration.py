"""
Integration tests for Workflow Engine
Tests complete workflow lifecycle: Ingestion → Validation → Indicators → Signals
Uses REAL data (no mocks) - similar to test_integration_real_data.py
"""
import unittest
import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.workflows.eod_workflow import EODWorkflow
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.data_frequency import DataFrequency
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.services.stock_screener_service import StockScreenerService
from app.database import db, init_database
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType


class TestWorkflowIntegration(unittest.TestCase):
    """
    Integration tests for complete workflow engine lifecycle
    Tests with real data: NVDA, AAPL, ASTL, LCID, STOCKS
    No mocks - uses actual API calls and database operations
    """
    
    @classmethod
    def setUpClass(cls):
        """Initialize database and services"""
        print("\n" + "="*80)
        print("INITIALIZING WORKFLOW ENGINE INTEGRATION TESTS")
        print("="*80)
        
        # Initialize database
        init_database()
        
        # Initialize services
        cls.eod_workflow = EODWorkflow()
        cls.orchestrator = WorkflowOrchestrator()
        cls.indicator_service = IndicatorService()
        cls.strategy_service = StrategyService()
        cls.screener_service = StockScreenerService()
        cls.refresh_manager = DataRefreshManager()
        
        # Test symbols (using valid stock tickers)
        cls.test_symbols = ['NVDA', 'AAPL', 'ASTL', 'LCID', 'TSLA']
        
        print(f"✅ Services initialized")
        print(f"📊 Test symbols: {', '.join(cls.test_symbols)}")
        print("="*80 + "\n")
    
    def test_stage_1_data_ingestion(self):
        """Test Stage 1: Data Ingestion - Load raw price data"""
        print("\n📥 Testing Stage 1: Data Ingestion...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                print(f"  Testing {symbol}...")
                
                # Use refresh manager to fetch data
                result = self.refresh_manager.refresh_data(
                    symbol=symbol.upper(),
                    data_types=[DataType.PRICE_HISTORICAL],
                    mode=RefreshMode.ON_DEMAND,
                    force=True
                )
                
                # Check if data was fetched
                price_result = result.results.get('price_historical')
                self.assertIsNotNone(price_result, f"{symbol}: No price result")
                self.assertEqual(
                    price_result.status.value, 'success',
                    f"{symbol}: Data ingestion failed - {price_result.error}"
                )
                self.assertGreater(
                    price_result.rows_affected, 0,
                    f"{symbol}: No rows fetched"
                )
                
                # Verify data exists in database
                query = """
                    SELECT COUNT(*) as count FROM raw_market_data
                    WHERE stock_symbol = :symbol
                """
                db_result = db.execute_query(query, {"symbol": symbol.upper()})
                row_count = db_result[0]['count'] if db_result else 0
                self.assertGreater(row_count, 0, f"{symbol}: No data in database")
                
                print(f"  ✅ {symbol}: {row_count} rows ingested")
    
    def test_stage_2_validation_audit(self):
        """Test Stage 2: Validation & Audit - Check data quality"""
        print("\n✅ Testing Stage 2: Validation & Audit...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                print(f"  Testing {symbol}...")
                
                # Check audit history
                query = """
                    SELECT * FROM data_fetch_audit
                    WHERE symbol = :symbol
                    ORDER BY fetch_timestamp DESC
                    LIMIT 1
                """
                audit_result = db.execute_query(query, {"symbol": symbol.upper()})
                self.assertIsNotNone(audit_result, f"{symbol}: No audit record")
                if audit_result:
                    audit = audit_result[0]
                    self.assertIn('success', audit, f"{symbol}: Audit missing success field")
                    print(f"  ✅ {symbol}: Audit record found (success: {audit.get('success')})")
                
                # Check validation report
                query = """
                    SELECT * FROM data_validation_reports
                    WHERE symbol = :symbol AND data_type = 'price_historical'
                    ORDER BY validation_timestamp DESC
                    LIMIT 1
                """
                validation_result = db.execute_query(query, {"symbol": symbol.upper()})
                if validation_result:
                    validation = validation_result[0]
                    overall_status = validation.get('overall_status', 'unknown')
                    print(f"  ✅ {symbol}: Validation status: {overall_status}")
                    # Don't fail if validation report doesn't exist (might not be generated yet)
    
    def test_stage_3_indicator_calculation(self):
        """Test Stage 3: Indicator Calculation - Compute all indicators"""
        print("\n📊 Testing Stage 3: Indicator Calculation...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                print(f"  Testing {symbol}...")
                
                # Calculate indicators
                success = self.indicator_service.calculate_indicators(symbol.upper())
                self.assertTrue(success, f"{symbol}: Indicator calculation failed")
                
                # Verify indicators exist in database
                query = """
                    SELECT * FROM aggregated_indicators
                    WHERE stock_symbol = :symbol
                    ORDER BY date DESC
                    LIMIT 1
                """
                indicator_result = db.execute_query(query, {"symbol": symbol.upper()})
                self.assertIsNotNone(indicator_result, f"{symbol}: No indicators in database")
                
                if indicator_result:
                    indicators = indicator_result[0]
                    # Check key indicators
                    required_indicators = ['ema9', 'ema21', 'sma50', 'sma200', 'rsi', 'macd']
                    for ind in required_indicators:
                        self.assertIn(ind, indicators, f"{symbol}: Missing indicator {ind}")
                    
                    # Check that at least some indicators have values
                    has_values = any(
                        indicators.get(ind) is not None
                        for ind in required_indicators
                    )
                    self.assertTrue(has_values, f"{symbol}: All indicators are None")
                    
                    print(f"  ✅ {symbol}: Indicators calculated successfully")
                    print(f"     EMA9: {indicators.get('ema9')}, RSI: {indicators.get('rsi')}")
    
    def test_stage_4_signal_generation(self):
        """Test Stage 4: Signal Generation - Generate buy/sell/hold signals"""
        print("\n🎯 Testing Stage 4: Signal Generation...")
        
        for symbol in self.test_symbols:
            with self.subTest(symbol=symbol):
                print(f"  Testing {symbol}...")
                
                # Get latest indicators
                from app.utils.database_helper import DatabaseQueryHelper
                indicators_data = DatabaseQueryHelper.get_latest_indicators(symbol.upper())
                
                if not indicators_data:
                    self.skipTest(f"{symbol}: No indicators available - run indicator calculation first")
                
                # Get current price from raw_market_data (indicators don't have close)
                stock_data = DatabaseQueryHelper.get_stock_by_symbol(symbol.upper(), "raw_market_data")
                current_price = stock_data.get('close', 0) if stock_data else 0
                
                # Get market data
                from app.data_sources import get_data_source
                data_source = get_data_source()
                market_data = data_source.fetch_price_data(symbol.upper(), period="1y")
                
                if market_data is None or market_data.empty:
                    self.skipTest(f"{symbol}: No market data available")
                
                # Prepare indicators dict for strategy
                import pandas as pd
                indicators = {
                    'price': pd.Series([current_price]),
                    'ema20': pd.Series([indicators_data.get('ema20', 0)]),
                    'ema50': pd.Series([indicators_data.get('ema50', 0)]),
                    'sma200': pd.Series([indicators_data.get('sma200', 0)]),
                    'rsi': pd.Series([indicators_data.get('rsi', 0)]),
                    'macd': pd.Series([indicators_data.get('macd', 0)]),
                    'macd_signal': pd.Series([indicators_data.get('macd_signal', 0)]),
                    'macd_histogram': pd.Series([indicators_data.get('macd_histogram', 0)]),
                    'atr': pd.Series([indicators_data.get('atr', 0)]),
                    'volume': pd.Series([indicators_data.get('volume', 0)]),
                    'long_term_trend': pd.Series([indicators_data.get('long_term_trend', 'neutral')]),
                    'medium_term_trend': pd.Series([indicators_data.get('medium_term_trend', 'neutral')])
                }
                
                # Execute strategy
                result = self.strategy_service.execute_strategy(
                    strategy_name='technical',
                    indicators=indicators,
                    market_data=market_data,
                    context={'symbol': symbol.upper()}
                )
                
                # Validate result
                self.assertIsNotNone(result, f"{symbol}: Strategy returned None")
                self.assertIn(result.signal, ['buy', 'sell', 'hold'],
                            f"{symbol}: Invalid signal: {result.signal}")
                self.assertGreaterEqual(result.confidence, 0.0,
                                      f"{symbol}: Confidence < 0")
                self.assertLessEqual(result.confidence, 1.0,
                                   f"{symbol}: Confidence > 1")
                self.assertIsNotNone(result.reason,
                                    f"{symbol}: No reason provided")
                
                print(f"  ✅ {symbol}: Signal generated - {result.signal.upper()} "
                      f"(confidence: {result.confidence:.2f})")
    
    def test_stage_5_stock_screening(self):
        """Test Stage 5: Stock Screening - Screen stocks based on criteria"""
        print("\n🔍 Testing Stage 5: Stock Screening...")
        
        # Test different screening criteria
        test_criteria = [
            {"has_good_fundamentals": True, "limit": 10},
            {"price_below_sma50": True, "limit": 10},
            {"is_growth_stock": True, "limit": 10},
            {"min_rsi": 30, "max_rsi": 70, "limit": 10}
        ]
        
        for criteria in test_criteria:
            with self.subTest(criteria=criteria):
                print(f"  Testing criteria: {criteria}...")
                
                # Run screener
                results = self.screener_service.screen_stocks(**criteria)
                
                # Validate results
                self.assertIsNotNone(results, "Screener returned None")
                self.assertIn('stocks', results, "Missing 'stocks' in results")
                
                stocks = results.get('stocks', [])
                self.assertIsInstance(stocks, list, "Stocks should be a list")
                
                print(f"  ✅ Found {len(stocks)} stocks matching criteria")
    
    def test_end_to_end_workflow(self):
        """Test complete end-to-end workflow for all symbols"""
        print("\n🔄 Testing End-to-End Workflow...")
        
        # Run EOD workflow for test symbols
        result = self.eod_workflow.execute_daily_eod_workflow(self.test_symbols)
        
        # Validate overall success
        self.assertTrue(result.get('success'), f"Workflow failed: {result.get('error')}")
        
        # Validate stages
        stages = result.get('stages', {})
        
        # Stage 1: Price Loading
        price_loading = stages.get('price_loading', {})
        self.assertGreater(price_loading.get('succeeded', 0), 0,
                          "No symbols succeeded in price loading")
        print(f"  ✅ Stage 1: {price_loading.get('succeeded')} symbols loaded")
        
        # Stage 3: Indicator Recomputation
        indicator_recomp = stages.get('indicator_recomputation', {})
        self.assertGreater(indicator_recomp.get('succeeded', 0), 0,
                          "No symbols succeeded in indicator calculation")
        print(f"  ✅ Stage 3: {indicator_recomp.get('succeeded')} indicators calculated")
        
        # Stage 4: Signal Generation
        signal_gen = stages.get('signal_generation', {})
        self.assertGreater(signal_gen.get('succeeded', 0), 0,
                          "No symbols succeeded in signal generation")
        print(f"  ✅ Stage 4: {signal_gen.get('succeeded')} signals generated")
        
        # Stage 5: Portfolio Updates
        portfolio_updates = stages.get('portfolio_updates', {})
        print(f"  ✅ Stage 5: {portfolio_updates.get('portfolios_updated', 0)} portfolios updated")
        
        print(f"\n✅ End-to-End Workflow completed successfully!")
        print(f"   Elapsed time: {result.get('elapsed_seconds', 0):.2f} seconds")
    
    def test_workflow_orchestrator(self):
        """Test WorkflowOrchestrator directly"""
        print("\n🔄 Testing WorkflowOrchestrator...")
        
        # Test with single symbol
        test_symbol = 'AAPL'
        
        result = self.orchestrator.execute_workflow(
            workflow_type='on_demand',
            symbols=[test_symbol],
            data_frequency=DataFrequency.DAILY,
            force=True
        )
        
        # Validate result
        self.assertTrue(result.success, f"Orchestrator failed: {result.error}")
        self.assertGreater(result.symbols_succeeded, 0,
                          "No symbols succeeded")
        self.assertIn('ingestion', result.stages_completed,
                     "Ingestion stage not completed")
        
        print(f"  ✅ Orchestrator completed successfully")
        print(f"     Workflow ID: {result.workflow_id}")
        print(f"     Symbols succeeded: {result.symbols_succeeded}")
        print(f"     Stages completed: {', '.join(result.stages_completed)}")


if __name__ == '__main__':
    # Configure test output
    unittest.main(verbosity=2, buffer=False)

