#!/usr/bin/env python3
"""
Test Application Schema Visibility
Tests if the application can see the updated database schema
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_app_schema_visibility():
    """Test if the application can see the updated schema"""
    try:
        print("🔍 Testing Application Schema Visibility")
        print("=" * 50)
        
        # Import the app's database module
        from app.database import db
        
        print("✅ Successfully imported app.database.db")
        
        # Test getting a session
        with db.get_session() as session:
            print("✅ Successfully created database session")
            
            # Check table schema from application's perspective
            from sqlalchemy import text
            
            result = session.execute(text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'financial_statements'
                ORDER BY ordinal_position
            """)).fetchall()
            
            print("📋 Financial statements table schema (from app):")
            for col in result:
                print(f"   - {col[0]}: {col[1]} (nullable: {col[2]}, default: {col[3]})")
            
            # Check if data_source column exists
            columns = [col[0] for col in result]
            if 'data_source' in columns:
                print("✅ 'data_source' column exists in application's view")
            else:
                print("❌ 'data_source' column missing from application's view")
                return False
            
            # Check constraints from application's perspective
            result = session.execute(text("""
                SELECT conname, contype, pg_get_constraintdef(oid) as definition
                FROM pg_constraint 
                WHERE conrelid = 'financial_statements'::regclass
            """)).fetchall()
            
            print("\n📋 Financial statements table constraints (from app):")
            for con in result:
                print(f"   - {con[0]}: {con[1]} - {con[2]}")
            
            # Check if primary key exists
            has_primary_key = any(con[1] == 'p' for con in result)
            if has_primary_key:
                print("✅ Primary key constraint exists in application's view")
            else:
                print("❌ Primary key constraint missing from application's view")
                return False
        
        print("✅ Application can see the updated schema correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Error checking application schema visibility: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_app_insert_with_session():
    """Test insert using the exact same session pattern as the application"""
    try:
        print("\n🔍 Testing Application Insert Pattern")
        print("=" * 50)
        
        from app.database import db
        from datetime import datetime, date
        import json
        
        # Use the exact same pattern as the refresh manager
        with db.get_session() as session:
            print("✅ Created session using app.db.get_session()")
            
            # Test the exact same SQL pattern as the application
            from sqlalchemy import text
            
            record = {
                'stock_symbol': 'TEST_APP',
                'period_type': 'annual',
                'statement_type': 'income_statement',
                'fiscal_period': date(2023, 12, 31),
                'payload': '{"date": "2023-12-31", "symbol": "TEST_APP", "test": true}',
                'data_source': 'test_app',
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            print("📝 Testing insert with application's session pattern...")
            
            session.execute(text("""
                INSERT INTO financial_statements 
                (stock_symbol, period_type, statement_type, fiscal_period, payload, data_source, created_at, updated_at)
                VALUES (:stock_symbol, :period_type, :statement_type, :fiscal_period, :payload, :data_source, :created_at, :updated_at)
                ON CONFLICT (stock_symbol, period_type, statement_type, fiscal_period)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    data_source = EXCLUDED.data_source,
                    updated_at = NOW()
            """), record)
            
            session.commit()
            print("✅ Application insert pattern successful!")
            
            # Verify the insert
            result = session.execute(text("""
                SELECT stock_symbol, data_source, payload::text as preview
                FROM financial_statements 
                WHERE stock_symbol = :stock_symbol
            """), {'stock_symbol': 'TEST_APP'}).fetchone()
            
            print(f"✅ Verification successful: {result}")
            
            # Clean up
            session.execute(text("""
                DELETE FROM financial_statements 
                WHERE stock_symbol = :stock_symbol
            """), {'stock_symbol': 'TEST_APP'})
            session.commit()
            print("✅ Test data cleaned up")
        
        return True
        
    except Exception as e:
        print(f"❌ Application insert pattern failed: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Test 1: Schema visibility
    if not test_app_schema_visibility():
        print("\n❌ Application cannot see updated schema - this is the issue!")
        exit(1)
    
    # Test 2: Insert pattern
    if not test_app_insert_with_session():
        print("\n❌ Application insert pattern fails - this is the issue!")
        exit(1)
    
    print("\n🎉 Application database tests passed!")
    print("The application should work correctly now.")
