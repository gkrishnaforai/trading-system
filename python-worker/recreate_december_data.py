#!/usr/bin/env python3
"""
Clear and recreate December 2025 test data for TQQQ
"""

import psycopg2
import os
from datetime import datetime, timedelta

def clear_and_recreate_data():
    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("🗑️  Clearing Existing Test Data")
        print("=" * 50)
        
        # Clear existing test data for December 2025
        cursor.execute("""
            DELETE FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-12-01' 
            AND date <= '2025-12-31'
            AND data_source = 'manual'
        """)
        
        deleted_count = cursor.rowcount
        conn.commit()
        print(f"✅ Cleared {deleted_count} existing test records")
        
        # Get template data from existing TQQQ records
        cursor.execute("""
            SELECT sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, atr, bb_width
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND sma_50 IS NOT NULL
            ORDER BY date DESC 
            LIMIT 1
        """)
        
        template = cursor.fetchone()
        
        if not template:
            print("❌ No template data found")
            return
        
        print(f"📊 Using template data: SMA50={template[0]:.2f}, RSI={template[3]:.2f}")
        
        # Create data for each trading day in December 2025
        trading_days = []
        current_date = datetime(2025, 12, 1).date()
        end_date = datetime(2025, 12, 31).date()
        
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() < 5:  # Monday-Friday
                trading_days.append(current_date)
            current_date += timedelta(days=1)
        
        print(f"📅 Creating data for {len(trading_days)} trading days in December 2025")
        
        # Generate realistic price progression
        base_sma50 = template[0] * 0.85  # Start lower in early December
        base_sma200 = template[1] * 0.83
        base_ema20 = template[2] * 0.85
        
        inserted_count = 0
        
        for i, date in enumerate(trading_days):
            # Create realistic progression (trending up through December)
            progression_factor = 1.0 + (i / len(trading_days)) * 0.15  # 15% increase over month
            
            # Add some daily volatility
            daily_variation = 0.98 + (i % 5) * 0.01  # Small daily variations
            
            sma_50 = base_sma50 * progression_factor * daily_variation
            sma_200 = base_sma200 * progression_factor * daily_variation
            ema_20 = base_ema20 * progression_factor * daily_variation
            
            # RSI oscillates between 30-70
            rsi_cycle = (i % 14) / 14.0  # 14-day cycle
            rsi_14 = 30 + (40 * (0.5 + 0.5 * (rsi_cycle - 0.5) * 2))  # Oscillate 30-70
            
            # MACD values
            macd = template[4] * progression_factor * (0.9 + (i % 3) * 0.1)
            macd_signal = template[5] * progression_factor * (0.9 + (i % 3) * 0.1)
            macd_hist = macd - macd_signal
            
            # Determine signal based on technical conditions
            if rsi_14 > 65 and ema_20 > sma_50:
                signal = 'sell'
                confidence = 0.6 + (rsi_14 - 65) / 35 * 0.3  # Higher confidence for overbought
            elif rsi_14 < 35 and ema_20 < sma_50:
                signal = 'buy'
                confidence = 0.6 + (35 - rsi_14) / 35 * 0.3  # Higher confidence for oversold
            else:
                signal = 'hold'
                confidence = 0.4 + abs(rsi_14 - 50) / 50 * 0.2  # Moderate confidence for neutral
            
            # Insert 2-3 records per day to simulate multiple calculations
            records_per_day = 2 + (i % 2)
            
            for record_num in range(records_per_day):
                # Small variations between records on same day
                record_variation = 1.0 + (record_num * 0.001)
                
                cursor.execute("""
                    INSERT INTO indicators_daily (
                        symbol, date, sma_50, sma_200, ema_20, rsi_14, 
                        macd, macd_signal, macd_hist, atr, bb_width,
                        signal, confidence_score, created_at, updated_at,
                        indicator_name, data_source
                    ) VALUES (
                        'TQQQ', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, NOW() - (%s * INTERVAL '1 minute'), NOW(),
                        NULL, 'manual'
                    )
                """, (
                    date,
                    sma_50 * record_variation,
                    sma_200 * record_variation,
                    ema_20 * record_variation,
                    rsi_14,
                    macd * record_variation,
                    macd_signal * record_variation,
                    macd_hist * record_variation,
                    template[7],  # ATR
                    template[8],  # BB Width
                    signal,
                    confidence,
                    record_num * 5  # Stagger timestamps
                ))
                
                inserted_count += 1
        
        conn.commit()
        
        print(f"✅ Successfully inserted {inserted_count} records for {len(trading_days)} trading days")
        print(f"📈 Price progression: {trading_days[0]} SMA50={base_sma50:.2f} → {trading_days[-1]} SMA50={sma_50:.2f}")
        
        # Verify the data
        cursor.execute("""
            SELECT date, COUNT(*) as count, AVG(sma_50) as avg_sma, AVG(rsi_14) as avg_rsi,
                   AVG(confidence_score) as avg_conf, string_agg(DISTINCT signal, ', ') as signals
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date >= '2025-12-01' AND date <= '2025-12-31'
            GROUP BY date
            ORDER BY date
            LIMIT 5
        """)
        
        sample_results = cursor.fetchall()
        print("\n📊 Sample of Created Data (first 5 days):")
        for date, count, avg_sma, avg_rsi, avg_conf, signals in sample_results:
            print(f"  {date}: {count} records, SMA50={avg_sma:.2f}, RSI={avg_rsi:.1f}, Conf={avg_conf:.2f}, Signals={signals}")
        
        print(f"\n🎯 December 2025 test data ready!")
        print(f"   Now you can backtest any date from 2025-12-01 to 2025-12-31")
        
        # Test specific dates you wanted
        test_dates = ['2025-12-17', '2025-12-19', '2025-12-31']
        print(f"\n🧪 Testing your requested dates:")
        
        for test_date in test_dates:
            cursor.execute("""
                SELECT sma_50, rsi_14, signal, confidence_score
                FROM indicators_daily 
                WHERE symbol = 'TQQQ' AND date = %s
                LIMIT 1
            """, (test_date,))
            
            result = cursor.fetchone()
            if result:
                sma50, rsi14, signal, conf = result
                print(f"  {test_date}: SMA50={sma50:.2f}, RSI={rsi14:.1f}, Signal={signal}, Conf={conf:.2f} ✅")
            else:
                print(f"  {test_date}: No data found ❌")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if conn:
            conn.rollback()

if __name__ == "__main__":
    clear_and_recreate_data()
