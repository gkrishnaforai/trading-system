#!/usr/bin/env python3
"""
Debug script to check indicators table structure and data
"""

import psycopg2
import os
from datetime import datetime

def debug_indicators_table():
    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("🔍 Debugging Indicators Table")
        print("=" * 50)
        
        # 1. Check table structure
        print("\n📋 Table Structure:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'indicators_daily' 
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        for col in columns:
            print(f"  {col[0]}: {col[1]} ({'NULL' if col[2] == 'YES' else 'NOT NULL'})")
        
        # 2. Check sample data
        print("\n📊 Sample Data (first 5 rows):")
        cursor.execute("SELECT * FROM indicators_daily LIMIT 5")
        rows = cursor.fetchall()
        
        if rows:
            # Get column names for header
            col_names = [desc[0] for desc in cursor.description]
            print(f"  Columns: {col_names}")
            
            for i, row in enumerate(rows):
                print(f"  Row {i+1}: {row}")
        else:
            print("  ❌ No data found")
        
        # 3. Check for TQQQ specifically
        print("\n🎯 TQQQ Data Check:")
        cursor.execute("SELECT COUNT(*) FROM indicators_daily WHERE symbol ILIKE '%TQQQ%'")
        tqqq_count = cursor.fetchone()[0]
        print(f"  TQQQ records: {tqqq_count}")
        
        if tqqq_count > 0:
            cursor.execute("""
                SELECT symbol, date, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal 
                FROM indicators_daily 
                WHERE symbol ILIKE '%TQQQ%' 
                ORDER BY date DESC 
                LIMIT 3
            """)
            tqqq_rows = cursor.fetchall()
            for row in tqqq_rows:
                print(f"  {row[0]} on {row[1]}: SMA50={row[2]}, RSI={row[5]}")
        
        # 4. Check date range
        print("\n📅 Date Range:")
        cursor.execute("SELECT MIN(date), MAX(date), COUNT(DISTINCT date) FROM indicators_daily")
        min_date, max_date, unique_dates = cursor.fetchone()
        print(f"  Range: {min_date} to {max_date}")
        print(f"  Unique dates: {unique_dates}")
        
        # 5. Check symbol distribution
        print("\n📈 Symbol Distribution:")
        cursor.execute("""
            SELECT symbol, COUNT(*) as count 
            FROM indicators_daily 
            GROUP BY symbol 
            ORDER BY count DESC 
            LIMIT 5
        """)
        symbols = cursor.fetchall()
        for symbol, count in symbols:
            print(f"  {symbol}: {count} records")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    debug_indicators_table()
