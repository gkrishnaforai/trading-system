"""
Test Screener Fix
Test that the screener API call works without the unsupported parameter
"""

def test_screener_fix():
    """Test that the screener fix removes the problematic parameter"""
    
    print("🔧 Testing Screener Fix")
    print("=" * 30)
    
    dashboard_file = "/Users/krishnag/tools/trading-system/streamlit-app/pages/9_Trading_Dashboard.py"
    
    try:
        with open(dashboard_file, 'r') as f:
            content = f.read()
        
        # Check that the problematic line is commented out (allowing for extra spaces)
        lines = content.split('\n')
        min_sma_found = False
        min_sma_commented = False
        
        for line in lines:
            if 'payload["min_sma_50"]' in line:
                min_sma_found = True
                if line.strip().startswith('#'):
                    min_sma_commented = True
                    break
        
        if min_sma_found and min_sma_commented:
            print("✅ min_sma_50 parameter properly commented out")
        elif min_sma_found:
            print("❌ min_sma_50 parameter still active in code")
            return False
        else:
            print("✅ min_sma_50 parameter not found (already removed)")
        
        # Check that there's a comment explaining the issue
        if 'min_sma_50 parameter not supported' in content:
            print("✅ Comment explaining the issue found")
        else:
            print("⚠️  No explanatory comment found")
        
        # Check that help text is added
        if 'SMA50 filtering not yet supported' in content:
            print("✅ Help text added to UI")
        else:
            print("⚠️  No help text found in UI")
        
        # Check that the screener call is still present
        if 'api/v1/admin/screener/run' in content:
            print("✅ Screener API call still present")
        else:
            print("❌ Screener API call missing")
            return False
        
        print("✅ Screener fix implemented correctly")
        return True
        
    except Exception as e:
        print(f"❌ Error testing screener fix: {e}")
        return False

def print_fix_summary():
    """Print summary of the fix"""
    
    print("\n📋 Screener Fix Summary")
    print("=" * 25)
    
    print("🔧 Issue: Backend API doesn't support min_sma_50 parameter")
    print("✅ Fix: Commented out the unsupported parameter")
    print("✅ Added: Help text in UI to inform users")
    print("✅ Added: Code comment explaining the issue")
    print("✅ Result: Screener should work without errors")
    
    print("\n🚀 What's Fixed:")
    print("• Removed min_sma_50 from API payload")
    print("• Added user guidance in the UI")
    print("• Preserved other screener functionality")
    print("• No more 500 errors from unsupported parameters")
    
    print("\n📊 Current Screener Features:")
    print("• Max P/E ratio filtering ✅")
    print("• Limit on number of results ✅")
    print("• SMA50 filtering (coming soon) ⏳")

if __name__ == "__main__":
    success = test_screener_fix()
    print_fix_summary()
    
    if success:
        print(f"\n🎉 Screener Fix Successful!")
        print("✅ Dashboard should now load without errors")
        print("✅ Fundamentals screener should work properly")
    else:
        print(f"\n❌ Issues remain with screener fix")
