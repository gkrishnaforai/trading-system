#!/usr/bin/env python3
"""
Quick script to check table structure
"""

import os
import psycopg2
from dotenv import load_dotenv

def check_table_structure():
    load_dotenv()
    database_url = os.getenv('DATABASE_URL')
    
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    # Check raw_market_data_daily structure
    print("🔍 Checking raw_market_data_daily table structure:")
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = 'raw_market_data_daily' 
        ORDER BY ordinal_position
    """)
    
    columns = cursor.fetchall()
    for col in columns:
        print(f"   {col[0]}: {col[1]} (nullable: {col[2]}, default: {col[3]})")
    
    # Check if symbol column exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'raw_market_data_daily' 
            AND column_name = 'symbol'
        )
    """)
    symbol_exists = cursor.fetchone()[0]
    
    print(f"\n📊 Symbol column exists: {symbol_exists}")
    
    # Check if date column exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'raw_market_data_daily' 
            AND column_name = 'date'
        )
    """)
    date_exists = cursor.fetchone()[0]
    
    print(f"📊 Date column exists: {date_exists}")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_table_structure()
