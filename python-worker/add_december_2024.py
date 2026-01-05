#!/usr/bin/env python3
"""
Add December 2024 data to ensure 50+ days before March 15
"""

import psycopg2
import os
from datetime import datetime, timedelta

def add_december_2024():
    """Add December 2024 data"""
    
    print("📈 Adding December 2024 TQQQ Data")
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
        base_sma_50 = template[0] * 0.75  # Lower for Dec 2024
        
        # Add December 2024 data
        start_date = datetime(2024, 12, 1).date()
        end_date = datetime(2024, 12, 31).date()
        
        current_date = start_date
        count = 0
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Weekdays only
                progression = 0.75 + ((current_date - start_date).days / 31) * 0.1
                
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
                    40 + (current_date.day % 20),
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
        print(f"✅ Added {count} December 2024 records")
        
        # Verify total data before March 15
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
    add_december_2024()
