#!/usr/bin/env python3
"""
Debug script to test specific date queries
"""

import psycopg2
import os
from datetime import datetime

def test_date_query():
    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("🔍 Testing Date Queries for TQQQ")
        print("=" * 50)
        
        # Test 1: Check exact date match
        print("\n📅 Test 1: Exact date match for 2025-12-31")
        cursor.execute("""
            SELECT symbol, date, sma_50, rsi_14 
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date = '2025-12-31'
        """)
        
        exact_results = cursor.fetchall()
        print(f"  Found {len(exact_results)} exact matches")
        for row in exact_results:
            print(f"    {row[0]} on {row[1]}: SMA50={row[2]}, RSI={row[3]}")
        
        # Test 2: Check date <= query (like the API uses)
        print("\n📅 Test 2: Date <= query for 2025-12-31")
        cursor.execute("""
            SELECT symbol, date, sma_50, rsi_14 
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date <= '2025-12-31'
            ORDER BY date DESC LIMIT 1
        """)
        
        le_results = cursor.fetchall()
        print(f"  Found {len(le_results)} results with date <= 2025-12-31")
        for row in le_results:
            print(f"    {row[0]} on {row[1]}: SMA50={row[2]}, RSI={row[3]}")
        
        # Test 3: Check date <= query for 2026-01-02 (working case)
        print("\n📅 Test 3: Date <= query for 2026-01-02 (working case)")
        cursor.execute("""
            SELECT symbol, date, sma_50, rsi_14 
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date <= '2026-01-02'
            ORDER BY date DESC LIMIT 1
        """)
        
        working_results = cursor.fetchall()
        print(f"  Found {len(working_results)} results with date <= 2026-01-02")
        for row in working_results:
            print(f"    {row[0]} on {row[1]}: SMA50={row[2]}, RSI={row[3]}")
        
        # Test 4: Check all TQQQ dates
        print("\n📅 Test 4: All TQQQ dates available")
        cursor.execute("""
            SELECT DISTINCT date, COUNT(*) as count
            FROM indicators_daily 
            WHERE symbol = 'TQQQ'
            GROUP BY date
            ORDER BY date DESC
        """)
        
        all_dates = cursor.fetchall()
        print(f"  TQQQ has data for {len(all_dates)} different dates:")
        for date, count in all_dates:
            print(f"    {date}: {count} records")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_date_query()
