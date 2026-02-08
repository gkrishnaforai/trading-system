#!/usr/bin/env python3
"""
Check actual column names for problematic tables
"""

import sys
sys.path.append('app')
from app.database import db

# Tables that are failing
problematic_tables = [
    "stock_grades", 
    "stock_consensus_history", 
    "income_statements", 
    "balance_sheets", 
    "cash_flow_statements", 
    "financial_ratios",
    "earnings_transcripts"
]

print("🔍 Checking column names for problematic tables...")
print("=" * 80)

for table in problematic_tables:
    print(f"\n📊 {table}:")
    try:
        cols_query = '''
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = :table_name
            ORDER BY ordinal_position;
        '''
        result = db.execute_query(cols_query, {'table_name': table})
        if result:
            # Look for date and symbol related columns
            date_columns = []
            symbol_columns = []
            for row in result:
                col_name = row["column_name"]
                if 'date' in col_name.lower():
                    date_columns.append(col_name)
                if 'symbol' in col_name.lower():
                    symbol_columns.append(col_name)
            
            print(f"  🔹 Date columns: {date_columns}")
            print(f"  🔹 Symbol columns: {symbol_columns}")
            
            # Show all columns for reference
            print(f"  🔹 All columns:")
            for row in result:
                print(f"    {row['column_name']}: {row['data_type']}")
        else:
            print(f"  ❌ No columns found")
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 80)
print("🎯 Check completed!")
