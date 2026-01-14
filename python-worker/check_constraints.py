#!/usr/bin/env python3
"""Check constraints on raw_market_data_intraday table"""

import sys
import os
sys.path.append('/app')

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("check_constraints")

def check_table_constraints():
    """Check constraints on raw_market_data_intraday table"""
    try:
        # Initialize database connection
        db.initialize()
        
        # Check all constraints
        constraints_query = """
            SELECT 
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name,
                tc.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'raw_market_data_intraday'
            ORDER BY tc.constraint_type, tc.constraint_name
        """
        
        result = db.execute_query(constraints_query)
        
        if result:
            print("📊 Current constraints on raw_market_data_intraday:")
            print("=" * 70)
            for constraint in result:
                print(f"• {constraint['constraint_type']}: {constraint['constraint_name']}")
                print(f"  Column: {constraint['column_name']}")
            print("=" * 70)
            print(f"Total constraints: {len(result)}")
        else:
            print("❌ No constraints found on raw_market_data_intraday")
        
        # Check primary key specifically
        pk_query = """
            SELECT 
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name,
                kcu.ordinal_position
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'raw_market_data_intraday'
            AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """
        
        pk_result = db.execute_query(pk_query)
        
        if pk_result:
            print("\n🔑 Primary Key columns:")
            for pk in pk_result:
                print(f"  • {pk['column_name']} (position: {pk['ordinal_position']})")
        else:
            print("\n❌ No primary key found")
        
        # Check unique constraints
        unique_query = """
            SELECT 
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name,
                kcu.ordinal_position
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'raw_market_data_intraday'
            AND tc.constraint_type = 'UNIQUE'
            ORDER BY tc.constraint_name, kcu.ordinal_position
        """
        
        unique_result = db.execute_query(unique_query)
        
        if unique_result:
            print("\n🔒 Unique constraints:")
            current_constraint = None
            for unique in unique_result:
                if unique['constraint_name'] != current_constraint:
                    print(f"  • {unique['constraint_name']}:")
                    current_constraint = unique['constraint_name']
                print(f"    - {unique['column_name']}")
        else:
            print("\n❌ No unique constraints found")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to check constraints: {e}")
        print(f"❌ Failed to check constraints: {str(e)}")
        return False
    finally:
        if db.engine:
            db.close()

if __name__ == "__main__":
    check_table_constraints()
