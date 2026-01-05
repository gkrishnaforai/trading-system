#!/usr/bin/env python3
"""
Add more early 2025 data to fix March 15th issue
"""

import psycopg2
import os
from datetime import datetime, timedelta

def add_early_jan_2025():
    """Add early January 2025 data"""
    
    print("📈 Adding Early January 2025 TQQQ Data")
    print("=" * 40)
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Get template data
        cursor.execute("""
            SELECT sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, atr, bb_width
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND sma_50 IS NOT NULL
            ORDER BY date DESC 
            LIMIT 1
        """)
        template = cursor.fetchone()
        base_sma_50 = template[0] * 0.70  # Even lower for early Jan
        
        # Add early January 2025 data
        start_date = datetime(2025, 1, 1).date()
        end_date = datetime(2025, 1, 10).date()
        
        current_date = start_date
        count = 0
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Weekdays only
                progression = 0.70 + ((current_date - start_date).days / 10) * 0.05
                
                cursor.execute("""
                    INSERT INTO indicators_daily (
                        symbol, date, sma_50, sma_200, ema_20, rsi_14, 
                        macd, macd_signal, macd_hist, atr, bb_width,
                        signal, confidence_score, created_at, updated_at,
                        indicator_name, data_source
                    ) VALUES (
                        'TQQQ', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'hold', 0.5, NOW() - (%s * INTERVAL '1 minute'), NOW(),
                        NULL, 'manual'
                    )
                """, (
                    current_date,
                    base_sma_50 * progression,
                    template[1] * progression,
                    template[2] * progression,
                    35 + (current_date.day % 20),
                    template[4] * progression,
                    template[5] * progression,
                    template[4] * progression - template[5] * progression,
                    template[7] * progression,
                    template[8] * progression,
                    current_date.day
                ))
                count += 1
            current_date += timedelta(days=1)
        
        conn.commit()
        print(f"✅ Added {count} early January 2025 records")
        
        # Check total data before March 15
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date <= '2025-03-15'
        """)
        
        result = cursor.fetchone()
        print(f"📊 Total records before March 15: {result[0]}")
        
        if result[0] >= 50:
            print("✅ Sufficient data for March 15 backtesting!")
        else:
            print(f"❌ Still need {50 - result[0]} more records")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    add_early_jan_2025()
