#!/usr/bin/env python3
"""
Quick test for the fundamentals repository fix
"""

import sys
import os

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database
from app.repositories.fundamentals_repository import FundamentalsRepository

def test_fundamentals_fix():
    """Test that fundamentals can be stored and retrieved correctly"""
    print("🧪 Testing fundamentals repository fix...")
    
    init_database()
    
    repo = FundamentalsRepository()
    
    # Test data
    test_symbol = "TEST"
    test_data = {
        "pe_ratio": 25.5,
        "debt_to_equity": 0.5,
        "return_on_equity": 0.15,
        "sector": "Technology"
    }
    
    try:
        # Test upsert
        print("📝 Testing upsert...")
        success = repo.upsert_fundamentals(test_symbol, test_data)
        if success:
            print("✅ Upsert successful")
        else:
            print("❌ Upsert failed")
            return False
        
        # Test fetch
        print("📖 Testing fetch...")
        retrieved_data = repo.fetch_by_symbol(test_symbol)
        if retrieved_data:
            print("✅ Fetch successful")
            print(f"   Retrieved {len(retrieved_data)} fields:")
            for key, value in retrieved_data.items():
                print(f"   - {key}: {value}")
            
            # Verify data integrity
            if retrieved_data.get("pe_ratio") == test_data["pe_ratio"]:
                print("✅ Data integrity verified")
            else:
                print("❌ Data integrity failed")
                return False
        else:
            print("❌ Fetch failed - no data returned")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_fundamentals_fix()
    if success:
        print("\n🎉 Fundamentals repository fix works correctly!")
    else:
        print("\n💥 Fix failed! Please check the errors above.")
