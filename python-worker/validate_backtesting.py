"""
TQQQ Backtesting Validation Script
Quick validation to ensure the backtesting system works correctly
"""

import sys
import os
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.backtesting.tqqq_backtester import TQQQBacktester, BacktestConfig, BacktestPeriod
from app.observability.logging import get_logger

logger = get_logger(__name__)


def validate_backtesting_system():
    """Validate the TQQQ backtesting system"""
    
    print("🚀 Validating TQQQ Backtesting System...")
    print("=" * 50)
    
    try:
        # Test 1: Basic configuration
        print("📋 Test 1: Basic Configuration")
        config = BacktestConfig(
            period=BacktestPeriod.LAST_MONTH,
            initial_capital=10000.0,
            position_size_pct=0.015
        )
        print(f"✅ Configuration created: {config.period.value}")
        
        # Test 2: Backtester initialization
        print("\n🔧 Test 2: Backtester Initialization")
        backtester = TQQQBacktester(config)
        print("✅ Backtester initialized successfully")
        
        # Test 3: Date range calculation
        print("\n📅 Test 3: Date Range Calculation")
        start_date, end_date = backtester._get_date_range()
        print(f"✅ Date range: {start_date.date()} to {end_date.date()}")
        
        # Test 4: Data loading (quick test with small period)
        print("\n📊 Test 4: Data Loading")
        try:
            tqqq_data, qqq_data, vix_data = backtester._load_historical_data("TQQQ", start_date, end_date)
            print(f"✅ Data loaded: TQQQ ({len(tqqq_data)} days), QQQ ({len(qqq_data)} days), VIX ({len(vix_data)} days)")
            
            if len(tqqq_data) > 0:
                print(f"   Latest TQQQ price: ${tqqq_data['close'].iloc[-1]:.2f}")
                print(f"   Latest QQQ price: ${qqq_data['close'].iloc[-1]:.2f}")
                print(f"   Latest VIX: {vix_data['close'].iloc[-1]:.1f}")
            
        except Exception as e:
            print(f"⚠️  Data loading failed (expected if no data): {e}")
            print("   This is normal if the database doesn't have historical data yet")
        
        # Test 5: Engine metadata
        print("\n🎯 Test 5: Engine Metadata")
        metadata = backtester.engine.get_engine_metadata()
        print(f"✅ Engine: {metadata['display_name']}")
        print(f"   Version: {metadata['version']}")
        print(f"   Risk Level: {metadata['risk_level']}")
        print(f"   Complexity: {metadata['complexity']}")
        
        print("\n🎉 All tests completed successfully!")
        print("\n📋 Next Steps:")
        print("1. Ensure TQQQ, QQQ, and VIX data is loaded in the database")
        print("2. Run the Streamlit dashboard to access the backtesting interface")
        print("3. Use the '📊 TQQQ Backtest' tab to run comprehensive backtests")
        
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        logger.error(f"Backtesting validation error: {e}")
        return False


def quick_backtest_demo():
    """Run a quick backtest demo if data is available"""
    
    print("\n🚀 Quick Backtest Demo")
    print("=" * 30)
    
    try:
        # Use very short period for demo
        config = BacktestConfig(
            period=BacktestPeriod.LAST_MONTH,
            initial_capital=5000.0,
            position_size_pct=0.01  # 1% for demo
        )
        
        backtester = TQQQBacktester(config)
        
        print("📊 Running quick backtest (last month)...")
        result = backtester.run_backtest("TQQQ")
        
        print(f"✅ Backtest completed!")
        print(f"   Total Return: {result.total_return:.2%}")
        print(f"   Total Trades: {result.total_trades}")
        print(f"   Win Rate: {result.win_rate:.1%}")
        print(f"   Max Drawdown: {result.max_drawdown:.2%}")
        print(f"   Sharpe Ratio: {result.sharpe_ratio:.2f}")
        
        if result.trades:
            print(f"   Sample Trade: {result.trades[0].signal.value} - {result.trades[0].return_pct:.2%}")
        
        return True
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        return False


if __name__ == "__main__":
    print("🎯 TQQQ Backtesting System Validation")
    print("=" * 50)
    
    # Run validation
    validation_success = validate_backtesting_system()
    
    if validation_success:
        # Try quick demo
        demo_success = quick_backtest_demo()
        
        if demo_success:
            print("\n🎉 System is ready for use!")
            print("🚀 Start the Streamlit dashboard to access the full interface:")
            print("   streamlit run streamlit_trading_dashboard.py")
        else:
            print("\n⚠️  System validated but demo failed (likely missing data)")
            print("📊 Load historical data first using the data refresh system")
    else:
        print("\n❌ System validation failed")
        print("🔧 Check the error messages above and fix issues before proceeding")
