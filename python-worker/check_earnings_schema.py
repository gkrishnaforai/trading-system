#!/usr/bin/env python3
"""Check actual table structure of earnings_data"""

import sys
import os
sys.path.append('/app')

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("check_earnings_schema")

def check_earnings_table_structure():
    """Check actual columns in earnings_data table"""
    try:
        # Initialize database connection
        db.initialize()
        
        # Get all columns in the table
        check_query = """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'earnings_data' 
            ORDER BY ordinal_position
        """
        
        result = db.execute_query(check_query)
        
        if result:
            print("📊 Current table structure for earnings_data:")
            print("=" * 60)
            for col in result:
                print(f"• {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
                if col['column_default']:
                    print(f"  Default: {col['column_default']}")
            print("=" * 60)
            print(f"Total columns: {len(result)}")
        else:
            print("❌ Table earnings_data not found or no columns")
        
        # Also check if table exists at all
        table_check = db.execute_query("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'earnings_data'
            ) as exists
        """)
        
        if table_check and table_check[0]['exists']:
            print("✅ Table exists")
        else:
            print("❌ Table does not exist")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to check earnings table structure: {e}")
        print(f"❌ Failed to check table structure: {str(e)}")
        return False
    finally:
        if db.engine:
            db.close()

if __name__ == "__main__":
    check_earnings_table_structure()
