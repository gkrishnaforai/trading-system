#!/usr/bin/env python3
"""
Debug the fundamentals fetch issue
"""

import sys
import os

# Add project root so imports work
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_database, db
from app.repositories.fundamentals_repository import FundamentalsRepository
import json

def debug_fundamentals_fetch():
    """Debug what's happening during fetch"""
    print("🔍 Debugging fundamentals fetch...")
    
    init_database()
    
    symbol = "TEST"
    
    # First, let's check what's actually in the database
    print("📋 Checking database contents...")
    try:
        query = """
            SELECT stock_symbol, as_of_date, source, payload, created_at, updated_at
            FROM fundamentals_snapshots
            WHERE stock_symbol = :symbol
            ORDER BY as_of_date DESC
            LIMIT 1
        """
        
        result = db.execute_query(query, {"symbol": symbol})
        
        if result and len(result) > 0:
            print("✅ Found data in database:")
            row = result[0]
            print(f"   stock_symbol: {row['stock_symbol']}")
            print(f"   as_of_date: {row['as_of_date']}")
            print(f"   source: {row['source']}")
            print(f"   payload type: {type(row['payload'])}")
            print(f"   payload value: {row['payload']}")
            
            # Test JSON parsing
            try:
                if isinstance(row['payload'], str):
                    parsed = json.loads(row['payload'])
                    print(f"   ✅ JSON parsed successfully: {parsed}")
                else:
                    print(f"   ❌ Payload is not a string: {type(row['payload'])}")
            except Exception as e:
                print(f"   ❌ JSON parsing failed: {e}")
        else:
            print("❌ No data found in database")
            
    except Exception as e:
        print(f"❌ Database query failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Now test the repository method
    print("\n🔧 Testing repository fetch method...")
    try:
        repo = FundamentalsRepository()
        data = repo.fetch_by_symbol(symbol)
        if data:
            print(f"✅ Repository fetch successful: {data}")
        else:
            print("❌ Repository fetch returned None")
    except Exception as e:
        print(f"❌ Repository fetch failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_fundamentals_fetch()
