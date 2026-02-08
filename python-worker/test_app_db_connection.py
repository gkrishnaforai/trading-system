#!/usr/bin/env python3
"""
Test Application Database Connection
Tests if the application can connect to the database the same way as the test script
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_app_db_connection():
    """Test database connection using the app's database module"""
    try:
        print("🔍 Testing Application Database Connection")
        print("=" * 50)
        
        # Import the app's database module
        from app.database import db
        
        print("✅ Successfully imported app.database.db")
        
        # Test getting a session
        with db.get_session() as session:
            print("✅ Successfully created database session")
            
            # Test a simple query
            result = session.execute("SELECT 1 as test").fetchone()
            print(f"✅ Database query successful: {result}")
            
            # Test the financial_statements table
            try:
                result = session.execute("SELECT COUNT(*) FROM financial_statements").fetchone()
                print(f"✅ Financial statements table exists with {result[0]} records")
            except Exception as e:
                print(f"❌ Error accessing financial_statements table: {e}")
                return False
        
        print("✅ Application database connection works perfectly!")
        return True
        
    except Exception as e:
        print(f"❌ Application database connection failed: {e}")
        print(f"Error type: {type(e).__name__}")
        return False

def test_app_sql_insert():
    """Test the exact same insert using the app's database module"""
    try:
        print("\n🔍 Testing Application SQL Insert")
        print("=" * 50)
        
        from app.database import db
        from datetime import datetime, date
        import json
        
        # Exact same record from the application
        record = {
            'stock_symbol': 'AAPL',
            'period_type': 'annual',
            'statement_type': 'income_statement',
            'fiscal_period': date(2026, 12, 31),
            'payload': '{"date": "2021-09-25", "symbol": "AAPL", "reportedCurrency": "USD"}',
            'data_source': 'unknown',
            'created_at': datetime(2026, 1, 21, 5, 57, 3, 928344),
            'updated_at': datetime(2026, 1, 21, 5, 57, 3, 928344)
        }
        
        print("📝 Testing insert with app's database module...")
        
        with db.get_session() as session:
            # Test the exact same SQL as the application
            from sqlalchemy import text
            
            sql = text("""
                INSERT INTO financial_statements 
                (stock_symbol, period_type, statement_type, fiscal_period, payload, data_source, created_at, updated_at)
                VALUES (:stock_symbol, :period_type, :statement_type, :fiscal_period, :payload, :data_source, :created_at, :updated_at)
                ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    data_source = EXCLUDED.data_source,
                    updated_at = NOW()
            """)
            
            session.execute(sql, record)
            session.commit()
            print("✅ Application SQL insert successful!")
            
            # Clean up
            session.execute(text("""
                DELETE FROM financial_statements 
                WHERE stock_symbol = :stock_symbol 
                  AND period_type = :period_type 
                  AND statement_type = :statement_type 
                  AND fiscal_period = :fiscal_period
            """), record)
            session.commit()
            print("✅ Test data cleaned up")
        
        return True
        
    except Exception as e:
        print(f"❌ Application SQL insert failed: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Test 1: App database connection
    if not test_app_db_connection():
        print("\n❌ App database connection failed - this is the issue!")
        exit(1)
    
    # Test 2: App SQL insert
    if not test_app_sql_insert():
        print("\n❌ App SQL insert failed - this is the issue!")
        exit(1)
    
    print("\n🎉 Application database tests passed!")
    print("The issue might be in the refresh manager logic itself.")
