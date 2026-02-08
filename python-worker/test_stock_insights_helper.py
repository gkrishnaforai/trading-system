#!/usr/bin/env python3
"""
Test Stock Insights JSON Serialization Fix
Tests that the helper method correctly serializes JSON
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_helper_method():
    """Test the helper method directly"""
    try:
        print("🔍 Testing Stock Insights Helper Method")
        print("=" * 50)
        
        # Import the refresh manager
        from app.data_management.refresh_manager import DataRefreshManager
        from datetime import datetime, date
        
        # Create an instance
        manager = DataRefreshManager()
        
        # Test data
        test_symbol = "TEST_SYMBOL"
        test_date = date(2026, 1, 21)
        test_source = "test_source"
        test_payload = {"financial_scores": {"symbol": "TEST", "score": 100}}
        
        print(f"📝 Testing with:")
        print(f"   - Symbol: {test_symbol}")
        print(f"   - Date: {test_date}")
        print(f"   - Source: {test_source}")
        print(f"   - Payload: {test_payload}")
        
        # Test the helper method
        print(f"\n🔧 Calling helper method...")
        result = manager._save_to_stock_insights_snapshots(
            test_symbol, 
            test_date, 
            test_source, 
            test_payload
        )
        
        print(f"✅ Helper method returned: {result}")
        
        # Verify the data was saved
        from app.database import db
        with db.get_session() as session:
            from sqlalchemy import text
            records = session.execute(text("""
                SELECT stock_symbol, insights_date, source, payload::text as payload_text
                FROM stock_insights_snapshots 
                WHERE stock_symbol = :symbol AND source = :source
                ORDER BY insights_date DESC
                LIMIT 1
            """), {"symbol": test_symbol, "source": test_source}).fetchall()
            
            if records:
                record = records[0]
                print(f"✅ Data saved successfully:")
                print(f"   - Symbol: {record[0]}")
                print(f"   - Date: {record[1]}")
                print(f"   - Source: {record[2]}")
                print(f"   - Payload: {record[3][:100]}...")
                
                # Clean up test data
                session.execute(text("""
                    DELETE FROM stock_insights_snapshots 
                    WHERE stock_symbol = :symbol AND source = :source
                """), {"symbol": test_symbol, "source": test_source})
                session.commit()
                print(f"✅ Test data cleaned up")
                
                return True
            else:
                print(f"❌ No data found in database")
                return False
        
    except Exception as e:
        print(f"❌ Error testing helper method: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_helper_method()
    if success:
        print("\n🎉 Helper method test passed!")
        print("The JSON serialization fix is working correctly.")
    else:
        print("\n❌ Helper method test failed!")
        print("There may be an issue with the fix.")
