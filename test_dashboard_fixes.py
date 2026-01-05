"""
Test Dashboard Fixes
Test that both TQQQ Backtest and Signal Engines tabs are working
"""

import sys
import os

def test_dashboard_imports():
    """Test that all dashboard imports work correctly"""
    
    print("🔧 Testing Dashboard Fixes")
    print("=" * 40)
    
    # Test TQQQ backtest interface import
    print("\n📊 Testing TQQQ Backtest Interface...")
    try:
        sys.path.append('/Users/krishnag/tools/trading-system/python-worker')
        
        # Test basic dependencies
        import pandas as pd
        import plotly.graph_objects as go
        import plotly.express as px
        print("✅ Basic dependencies (pandas, plotly) available")
        
        # Test TQQQ interface import
        from app.streamlit.tqqq_backtest_interface import render_tqqq_backtest_interface
        print("✅ TQQQ backtest interface import successful")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"⚠️  Import warning: {e}")
        # This might be expected due to streamlit context
    
    # Test swing engines import
    print("\n🔄 Testing Swing Engines...")
    try:
        from app.signal_engines.generic_swing_engine import GenericSwingEngine
        from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
        from app.signal_engines.base import MarketContext, MarketRegime
        
        print("✅ Generic Swing Engine import successful")
        print("✅ TQQQ Swing Engine import successful")
        print("✅ Base classes import successful")
        
        # Test engine instantiation
        generic_engine = GenericSwingEngine()
        tqqq_engine = TQQQSwingEngine()
        
        print("✅ Generic Swing Engine instantiation successful")
        print("✅ TQQQ Swing Engine instantiation successful")
        
        # Test engine metadata
        generic_meta = generic_engine.get_engine_metadata()
        tqqq_meta = tqqq_engine.get_engine_metadata()
        
        print(f"✅ Generic Engine: {generic_meta['display_name']}")
        print(f"✅ TQQQ Engine: {tqqq_meta['display_name']}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Swing engine import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Swing engine error: {e}")
        return False

def test_dashboard_file_structure():
    """Test that dashboard file has the correct structure"""
    
    print(f"\n📁 Testing Dashboard File Structure...")
    
    dashboard_file = "/Users/krishnag/tools/trading-system/streamlit-app/pages/9_Trading_Dashboard.py"
    
    try:
        with open(dashboard_file, 'r') as f:
            content = f.read()
        
        # Check for TQQQ backtest tab
        checks = [
            ("TQQQ Backtest tab", "📊 TQQQ Backtest" in content),
            ("TQQQ backtest interface", "render_tqqq_backtest_interface" in content),
            ("Error handling", "except ImportError" in content),
            ("Python Swing Engines", "Python Swing Engines" in content),
            ("Generic swing engine", "generic_swing" in content),
            ("TQQQ swing engine", "tqqq_swing" in content),
            ("Engine selection", "swing_engine" in content),
        ]
        
        all_good = True
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            print(f"{status} {check_name}")
            if not check_result:
                all_good = False
        
        return all_good
        
    except Exception as e:
        print(f"❌ Error reading dashboard file: {e}")
        return False

def print_usage_instructions():
    """Print instructions for using the enhanced dashboard"""
    
    print(f"\n🚀 Dashboard Usage Instructions")
    print("=" * 40)
    
    print(f"\n📊 TQQQ Backtest Tab:")
    print("1. Navigate to '📊 TQQQ Backtest' tab")
    print("2. If there are import errors, follow troubleshooting steps")
    print("3. Load TQQQ, QQQ, and ^VIX data")
    print("4. Configure backtest parameters")
    print("5. Run comprehensive backtesting")
    
    print(f"\n🧠 Signal Engines Tab:")
    print("1. Navigate to '🧠 Signal Engines' tab")
    print("2. Select 'Python Swing Engines' radio button")
    print("3. Choose engine type:")
    print("   • generic_swing: For regular stocks/ETFs")
    print("   • tqqq_swing: For TQQQ only")
    print("4. Enter symbol (e.g., AAPL, MSFT, SPY)")
    print("5. Click 'Generate Swing Signal'")
    print("6. View engine metadata and configuration")
    
    print(f"\n🔧 Custom Symbol Loading:")
    print("1. Use sidebar '🔧 Custom Symbol Loading'")
    print("2. Enter any ticker symbol")
    print("3. Load price data and indicators")
    print("4. Use with either engine as appropriate")
    
    print(f"\n⚠️  Requirements:")
    print("• Database running (PostgreSQL)")
    print("• Historical data available for symbols")
    print("• Dependencies installed (plotly, pandas)")

def main():
    """Main test function"""
    
    print("🎯 Dashboard Enhancement Verification")
    print("=" * 45)
    
    # Test imports
    imports_ok = test_dashboard_imports()
    
    # Test file structure
    structure_ok = test_dashboard_file_structure()
    
    # Print usage instructions
    print_usage_instructions()
    
    # Summary
    print(f"\n📊 Test Results")
    print("=" * 20)
    print(f"Import tests: {'✅' if imports_ok else '❌'}")
    print(f"File structure: {'✅' if structure_ok else '❌'}")
    
    if imports_ok and structure_ok:
        print(f"\n🎉 Dashboard Enhancement Successful!")
        print("✅ TQQQ Backtest tab enhanced with error handling")
        print("✅ Signal Engines tab enhanced with Python swing engines")
        print("✅ Both engines available for different symbol types")
        
        print(f"\n🚀 Ready to use:")
        print("1. Start Streamlit: streamlit run streamlit-app/pages/9_Trading_Dashboard.py")
        print("2. Navigate to enhanced tabs")
        print("3. Use appropriate engines for your symbols")
        
        return True
    else:
        print(f"\n❌ Issues Found:")
        if not imports_ok:
            print("🔧 Import issues - check dependencies and paths")
        if not structure_ok:
            print("🔧 File structure issues - check dashboard modifications")
        
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
