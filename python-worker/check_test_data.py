#!/usr/bin/env python3
"""
Check and update existing test data for December 31, 2025
"""

import psycopg2
import os
from datetime import datetime

def check_and_update_data():
    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("🔍 Checking Existing Test Data")
        print("=" * 50)
        
        # Check what data exists for December 2025
        cursor.execute("""
            SELECT date, COUNT(*) as count, 
                   AVG(sma_50) as avg_sma, 
                   AVG(rsi_14) as avg_rsi,
                   AVG(confidence_score) as avg_conf
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date >= '2025-12-24' AND date <= '2025-12-31'
            GROUP BY date
            ORDER BY date
        """)
        
        existing_data = cursor.fetchall()
        print("📊 Existing TQQQ Data for December 24-31, 2025:")
        
        if not existing_data:
            print("  ❌ No data found for December 24-31, 2025")
        else:
            for date, count, avg_sma, avg_rsi, avg_conf in existing_data:
                print(f"  {date}: {count} records, SMA50={avg_sma:.2f}, RSI={avg_rsi:.2f}, Conf={avg_conf:.2f}")
        
        # Check all available dates for TQQQ
        cursor.execute("""
            SELECT date, COUNT(*) as count
            FROM indicators_daily 
            WHERE symbol = 'TQQQ'
            GROUP BY date
            ORDER BY date
        """)
        
        all_dates = cursor.fetchall()
        print(f"\n📅 All TQQQ Available Dates ({len(all_dates)} total):")
        for date, count in all_dates:
            print(f"  {date}: {count} records")
        
        # If December 31 data exists but has null indicators, update it
        cursor.execute("""
            SELECT sma_50, rsi_14, signal, confidence_score
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date = '2025-12-31'
            LIMIT 1
        """)
        
        dec31_data = cursor.fetchone()
        
        if dec31_data:
            sma50, rsi14, signal, conf = dec31_data
            print(f"\n🎯 December 31, 2025 Sample Data:")
            print(f"  SMA50: {sma50}, RSI: {rsi14}, Signal: {signal}, Conf: {conf}")
            
            if sma50 is None or rsi14 is None:
                print("  ⚠️  Data has null values - updating with test data...")
                
                # Get template from latest working data
                cursor.execute("""
                    SELECT sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, atr, bb_width
                    FROM indicators_daily 
                    WHERE symbol = 'TQQQ' AND sma_50 IS NOT NULL
                    ORDER BY date DESC 
                    LIMIT 1
                """)
                
                template = cursor.fetchone()
                
                if template:
                    # Update the null records with proper test data
                    cursor.execute("""
                        UPDATE indicators_daily 
                        SET 
                            sma_50 = %s,
                            sma_200 = %s,
                            ema_20 = %s,
                            rsi_14 = %s,
                            macd = %s,
                            macd_signal = %s,
                            macd_hist = %s,
                            atr = %s,
                            bb_width = %s,
                            signal = 'sell',
                            confidence_score = 0.7,
                            updated_at = NOW()
                        WHERE symbol = 'TQQQ' AND date = '2025-12-31' AND (sma_50 IS NULL OR rsi_14 IS NULL)
                    """, template)
                    
                    conn.commit()
                    print("  ✅ Updated December 31, 2025 with test data")
                else:
                    print("  ❌ No template data found")
            else:
                print("  ✅ December 31, 2025 data looks good!")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_and_update_data()
