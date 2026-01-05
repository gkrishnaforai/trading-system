#!/usr/bin/env python3
"""
Check data availability around 2025-08-22
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
from datetime import datetime

def check_data_availability():
    """Check data availability around 2025-08-22"""
    
    print("🔍 CHECKING DATA AVAILABILITY AROUND 2025-08-22")
    print("=" * 50)
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Check data availability around 2025-08-22
        cursor.execute("""
            SELECT i.date, r.close, i.rsi_14 
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = 'TQQQ' 
            AND i.date >= '2025-08-20' 
            AND i.date <= '2025-08-27'
            ORDER BY i.date
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ No data found around 2025-08-22")
            return
        
        df = pd.DataFrame(rows, columns=['date', 'close', 'rsi'])
        df['date'] = pd.to_datetime(df['date'])
        
        print('Available dates around 2025-08-22:')
        for i, row in df.iterrows():
            print(f"  {row['date'].strftime('%Y-%m-%d')}: Close=${row['close']:.2f}, RSI={row['rsi']:.1f}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_data_availability()
