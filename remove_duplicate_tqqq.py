"""
Remove Duplicate TQQQ Backtest from Python-Worker
Maintain DRY principles by removing the duplicate implementation
"""

import sys
import os

def remove_duplicate_tqqq_backtest():
    """Remove the TQQQ backtest tab from python-worker dashboard"""
    
    print("🗑️ Removing Duplicate TQQQ Backtest from Python-Worker")
    print("=" * 55)
    
    dashboard_file = "/Users/krishnag/tools/trading-system/python-worker/streamlit_trading_dashboard.py"
    
    try:
        with open(dashboard_file, 'r') as f:
            content = f.read()
        
        # Check if TQQQ backtest tab exists
        if "📊 TQQQ Backtest" not in content:
            print("✅ No TQQQ Backtest tab found in python-worker dashboard")
            return True
        
        print("🔍 Found TQQQ Backtest tab in python-worker dashboard")
        
        # Remove TQQQ backtest from tabs list
        lines = content.split('\n')
        new_lines = []
        skip_next = False
        
        for i, line in enumerate(lines):
            # Skip the TQQQ backtest tab line
            if "📊 TQQQ Backtest" in line and "tab" in line and i > 0:
                print("✅ Removing TQQQ Backtest from tabs list")
                continue
            
            # Remove tab11 variable and TQQQ backtest tab content
            if "tab11" in line and "TQQQ" in lines[i+1] if i+1 < len(lines) else False:
                print("✅ Removing tab11 variable and content")
                skip_next = True
                continue
            
            if skip_next:
                if line.strip().startswith("with tab"):
                    skip_next = False
                continue
            
            new_lines.append(line)
        
        # Write back the updated content
        with open(dashboard_file, 'w') as f:
            f.write('\n'.join(new_lines))
        
        print("✅ Successfully removed duplicate TQQQ Backtest from python-worker")
        return True
        
    except Exception as e:
        print(f"❌ Error removing duplicate: {e}")
        return False

def verify_removal():
    """Verify that the duplicate was removed"""
    
    print(f"\n🔍 Verifying Removal")
    print("=" * 25)
    
    dashboard_file = "/Users/krishnag/tools/trading-system/python-worker/streamlit_trading_dashboard.py"
    
    try:
        with open(dashboard_file, 'r') as f:
            content = f.read()
        
        if "📊 TQQQ Backtest" in content:
            print("❌ TQQQ Backtest still found in python-worker")
            return False
        else:
            print("✅ TQQQ Backtest successfully removed from python-worker")
            return True
        
    except Exception as e:
        print(f"❌ Error verifying removal: {e}")
        return False

def verify_streamlit_app_integration():
    """Verify that streamlit-app still has the TQQQ backtest"""
    
    print(f"\n🔍 Verifying Streamlit-App Integration")
    print("=" * 40)
    
    dashboard_file = "/Users/krishnag/tools/trading-system/streamlit-app/pages/9_Trading_Dashboard.py"
    
    try:
        with open(dashboard_file, 'r') as f:
            content = f.read()
        
        checks = [
            ("📊 TQQQ Backtest tab", "📊 TQQQ Backtest" in content),
            ("tab_tqqq_backtest variable", "tab_tqqq_backtest" in content),
            ("Import statement", "render_tqqq_backtest_interface" in content),
            ("Function call", "render_tqqq_backtest_interface()" in content),
        ]
        
        all_good = True
        
        for check_name, check_result in checks:
            status = "✅" if check_result else "❌"
            print(f"{status} {check_name}")
            if not check_result:
                all_good = False
        
        return all_good
        
    except Exception as e:
        print(f"❌ Error verifying streamlit-app: {e}")
        return False

def main():
    """Main function"""
    
    print("🎯 DRY Cleanup: Remove Duplicate TQQQ Backtest")
    print("=" * 50)
    
    # Remove duplicate from python-worker
    removal_success = remove_duplicate_tqqq_backtest()
    
    # Verify removal
    if removal_success:
        verify_success = verify_removal()
    else:
        verify_success = False
    
    # Verify streamlit-app still works
    streamlit_success = verify_streamlit_app_integration()
    
    # Summary
    print(f"\n📊 Cleanup Results")
    print("=" * 20)
    print(f"Python-worker removal: {'✅' if removal_success and verify_success else '❌'}")
    print(f"Streamlit-app integration: {'✅' if streamlit_success else '❌'}")
    
    if removal_success and verify_success and streamlit_success:
        print(f"\n🎉 DRY Cleanup Successful!")
        print("✅ Duplicate TQQQ Backtest removed from python-worker")
        print("✅ TQQQ Backtest remains in streamlit-app")
        print("✅ Single source of truth maintained")
        
        print(f"\n🚀 Next Steps:")
        print("1. Use the streamlit-app dashboard")
        print("2. Navigate to '📊 TQQQ Backtest' tab")
        print("3. All TQQQ backtesting functionality available")
        
        return True
    else:
        print(f"\n❌ Cleanup Issues Found")
        if not removal_success:
            print("🔧 Failed to remove duplicate from python-worker")
        if not verify_success:
            print("🔧 Verification of removal failed")
        if not streamlit_success:
            print("🔧 Streamlit-app integration issues")
        
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
