#!/usr/bin/env python3
"""
Direct Macro Refresh Script
Runs the macro refresh service to load VIX and other market data
"""

import os
import sys
from dotenv import load_dotenv

def refresh_macro_data():
    """Run macro refresh service to load VIX data"""
    
    load_dotenv()
    
    print("🔄 Running Macro Data Refresh...")
    
    try:
        # Import the macro refresh service
        from app.services.macro_refresh_service import MacroRefreshService
        
        # Create service instance
        service = MacroRefreshService()
        
        # Run the refresh
        print("📈 Refreshing macro data (VIX, NASDAQ, yields, breadth)...")
        result = service.refresh_daily_macro_snapshot()
        
        print("✅ Macro refresh completed!")
        print(f"📊 Results: {result}")
        
        # Show VIX data
        if result and 'vix_close' in result:
            print(f"🎯 VIX Level: {result['vix_close']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during macro refresh: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = refresh_macro_data()
    
    if success:
        print("\n📋 Next Steps:")
        print("1. Check VIX data:")
        print("   curl http://localhost:8001/admin/data-summary/macro_market_data")
        print("2. Test stock analysis with VIX:")
        print("   curl -X POST http://localhost:8001/api/v1/universal/backtest \\")
        print("        -H 'Content-Type: application/json' \\")
        print("        -d '{\"symbol\": \"AAPL\", \"analysis_type\": \"comprehensive\"}'")
    else:
        print("❌ Macro refresh failed")
        sys.exit(1)
