"""
Test TQQQ Backtest Integration
Test that the TQQQ backtest interface can be imported and used in the main dashboard
"""

import sys
import os

def test_tqqq_backtest_import():
    """Test importing the TQQQ backtest interface from the streamlit-app perspective"""
    
    print("🎯 Testing TQQQ Backtest Integration")
    print("=" * 50)
    
    try:
        # Simulate the import path from the streamlit-app
        streamlit_app_dir = "/Users/krishnag/tools/trading-system/streamlit-app"
        python_worker_dir = "/Users/krishnag/tools/trading-system/python-worker"
        
        # Add python-worker to path (like the dashboard does)
        sys.path.append(python_worker_dir)
        
        print(f"📁 Streamlit app directory: {streamlit_app_dir}")
        print(f"📁 Python worker directory: {python_worker_dir}")
        print(f"🐍 Python path includes python-worker: {python_worker_dir in sys.path}")
        
        # Test the import
        print("\n🔍 Testing import...")
        from app.streamlit.tqqq_backtest_interface import render_tqqq_backtest_interface
        
        print("✅ Successfully imported render_tqqq_backtest_interface")
        
        # Test that it's callable
        if callable(render_tqqq_backtest_interface):
            print("✅ render_tqqq_backtest_interface is callable")
        else:
            print("❌ render_tqqq_backtest_interface is not callable")
            return False
        
        # Test importing other components
        print("\n🔍 Testing component imports...")
        from app.backtesting.tqqq_backtester import TQQQBacktester, BacktestConfig
        from app.signal_engines.tqqq_swing_engine import TQQQSwingEngine
        
        print("✅ Successfully imported TQQQBacktester and BacktestConfig")
        print("✅ Successfully imported TQQQSwingEngine")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("\n🔧 Possible solutions:")
        print("1. Ensure python-worker directory exists")
        print("2. Check that all required files are in python-worker")
        print("3. Verify dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_file_paths():
    """Test that all required files exist"""
    
    print(f"\n📁 Checking File Paths")
    print("=" * 30)
    
    base_dir = "/Users/krishnag/tools/trading-system"
    
    required_files = [
        "python-worker/app/streamlit/tqqq_backtest_interface.py",
        "python-worker/app/backtesting/tqqq_backtester.py", 
        "python-worker/app/signal_engines/tqqq_swing_engine.py",
        "python-worker/app/backtesting/__init__.py",
        "python-worker/app/utils/technical_indicators.py",
        "streamlit-app/pages/9_Trading_Dashboard.py"
    ]
    
    all_exist = True
    
    for file_path in required_files:
        full_path = os.path.join(base_dir, file_path)
        exists = os.path.exists(full_path)
        status = "✅" if exists else "❌"
        print(f"{status} {file_path}")
        
        if not exists:
            all_exist = False
    
    return all_exist

def test_dashboard_integration():
    """Test that the dashboard integration is correct"""
    
    print(f"\n🔧 Checking Dashboard Integration")
    print("=" * 40)
    
    dashboard_file = "/Users/krishnag/tools/trading-system/streamlit-app/pages/9_Trading_Dashboard.py"
    
    try:
        with open(dashboard_file, 'r') as f:
            content = f.read()
        
        # Check for TQQQ backtest tab
        if "📊 TQQQ Backtest" in content:
            print("✅ TQQQ Backtest tab added to tabs list")
        else:
            print("❌ TQQQ Backtest tab not found in tabs list")
            return False
        
        # Check for tab_tqqq_backtest variable
        if "tab_tqqq_backtest" in content:
            print("✅ tab_tqqq_backtest variable defined")
        else:
            print("❌ tab_tqqq_backtest variable not found")
            return False
        
        # Check for import statement
        if "from app.streamlit.tqqq_backtest_interface import render_tqqq_backtest_interface" in content:
            print("✅ Import statement added")
        else:
            print("❌ Import statement not found")
            return False
        
        # Check for function call
        if "render_tqqq_backtest_interface()" in content:
            print("✅ Function call added")
        else:
            print("❌ Function call not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking dashboard: {e}")
        return False

def main():
    """Main test function"""
    
    print("🎯 TQQQ Backtest Integration Test")
    print("=" * 40)
    
    # Test file paths
    files_ok = test_file_paths()
    
    # Test dashboard integration
    dashboard_ok = test_dashboard_integration()
    
    # Test imports
    imports_ok = test_tqqq_backtest_import()
    
    # Summary
    print(f"\n📊 Integration Test Results")
    print("=" * 30)
    print(f"Files exist: {'✅' if files_ok else '❌'}")
    print(f"Dashboard integration: {'✅' if dashboard_ok else '❌'}")
    print(f"Import test: {'✅' if imports_ok else '❌'}")
    
    if files_ok and dashboard_ok and imports_ok:
        print(f"\n🎉 Integration Test PASSED!")
        print("✅ TQQQ Backtest is ready to use in the main dashboard")
        
        print(f"\n🚀 Next Steps:")
        print("1. Start the Streamlit app")
        print("2. Navigate to the '📊 TQQQ Backtest' tab")
        print("3. Load TQQQ, QQQ, and ^VIX data")
        print("4. Run backtests and analyze results")
        
        return True
    else:
        print(f"\n❌ Integration Test FAILED!")
        print("🔧 Check the errors above and fix issues")
        
        if not files_ok:
            print("📁 Missing files - ensure python-worker directory is complete")
        if not dashboard_ok:
            print("🔧 Dashboard integration incomplete - check the tab addition")
        if not imports_ok:
            print("🐍 Import issues - check Python path and dependencies")
        
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
