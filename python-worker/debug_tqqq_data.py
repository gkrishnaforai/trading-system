#!/usr/bin/env python3
"""
Debug TQQQ engine data retrieval issues
"""

import psycopg2
import os
from datetime import datetime, timedelta

def debug_tqqq_data():
    """Debug TQQQ engine data retrieval"""
    
    print("🔍 Debugging TQQQ Engine Data Retrieval")
    print("=" * 50)
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check data availability for March 15
        print("📊 Checking TQQQ data availability for March 15, 2025:")
        
        # Check raw price data
        cursor.execute("""
            SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest
            FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ' AND date <= '2025-03-15'
        """)
        
        price_result = cursor.fetchone()
        print(f"  📈 Raw price data: {price_result[0]} records ({price_result[1]} to {price_result[2]})")
        
        # Check indicators data
        cursor.execute("""
            SELECT COUNT(*) as count, MIN(date) as earliest, MAX(date) as latest
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date <= '2025-03-15'
        """)
        
        indicator_result = cursor.fetchone()
        print(f"  📊 Indicators data: {indicator_result[0]} records ({indicator_result[1]} to {indicator_result[2]})")
        
        # Check what the API is actually getting
        print(f"\n🔍 API Data Retrieval Analysis:")
        print(f"  Expected: 83+ records before March 15")
        print(f"  Actual: {indicator_result[0]} records")
        
        # Check if there's a date filtering issue
        cursor.execute("""
            SELECT date, sma_50, rsi_14
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date <= '2025-03-15'
            ORDER BY date DESC
            LIMIT 5
        """)
        
        recent_data = cursor.fetchall()
        print(f"\n📅 Recent indicators before March 15:")
        for row in recent_data:
            print(f"  {row[0]}: SMA50=${row[1]:.2f}, RSI={row[2]:.1f}")
        
        # Check if there's a specific issue with March 15th
        cursor.execute("""
            SELECT * FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date = '2025-03-15'
        """)
        
        march15_data = cursor.fetchall()
        print(f"\n📅 March 15th specific data: {len(march15_data)} records")
        if march15_data:
            for row in march15_data:
                print(f"  {row}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    debug_tqqq_data()
