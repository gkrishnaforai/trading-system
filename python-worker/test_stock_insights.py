#!/usr/bin/env python3
"""
Quick test for StockInsightsService initialization
"""

import sys
import os

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database
from app.services.stock_insights_service import StockInsightsService

def test_stock_insights():
    """Test StockInsightsService initialization and basic functionality"""
    print("🧪 Testing StockInsightsService...")
    
    # Initialize database
    init_database()
    
    try:
        # Test service initialization
        service = StockInsightsService()
        print("✅ StockInsightsService initialized successfully!")
        
        # Test getting available strategies
        strategies = service.get_available_strategies()
        print(f"✅ Found {len(strategies)} available strategies:")
        for name, desc in strategies.items():
            print(f"  - {name}: {desc}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_stock_insights()
    if success:
        print("\n🎉 All tests passed! The StockInsightsService is ready to use.")
    else:
        print("\n💥 Tests failed! Please check the errors above.")
