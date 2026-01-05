#!/usr/bin/env python3
"""
Create September-October 2025 test data for TQQQ using existing template
"""

import psycopg2
import os
from datetime import datetime, timedelta

def create_sep_oct_data():
    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("🗑️  Clearing Existing Sep-Oct Test Data")
        print("=" * 50)
        
        # Clear existing test data for Sep-Oct 2025
        cursor.execute("""
            DELETE FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
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
        
        print("\n📈 Creating September-October 2025 Test Data")
        print("=" * 50)
        
        # Create realistic progression for Sep-Oct 2025
        base_sma_50 = template[0]
        base_sma_200 = template[1]
        base_ema_20 = template[2]
        base_rsi = template[3]
        base_macd = template[4]
        base_macd_signal = template[5]
        base_macd_hist = template[6]
        base_atr = template[7]
        base_bb_width = template[8]
        
        # September: Start high, decline through month
        # October: Continue decline, then recovery
        
        sep_oct_dates = []
        current_date = datetime(2025, 9, 1).date()
        end_date = datetime(2025, 10, 31).date()
        
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Weekdays only
                sep_oct_dates.append(current_date)
            current_date += timedelta(days=1)
        
        inserted_count = 0
        
        for i, date in enumerate(sep_oct_dates):
            # Calculate realistic progression
            day_progress = i / len(sep_oct_dates)
            
            # September: Decline from high to low
            # October: Continue decline then recovery
            if date.month == 9:
                # September: Decline from $60 to $45
                price_factor = 1.0 - (day_progress * 2.0) * 0.25  # 25% decline
                rsi_factor = 1.0 - (day_progress * 2.0) * 0.3   # RSI drops from 70 to 40
            else:
                # October: Continue decline then recovery
                oct_progress = (date.day - 1) / 31
                if oct_progress < 0.7:  # First 70% of month: further decline
                    price_factor = 0.75 - (oct_progress * 0.7) * 0.2  # Additional 20% decline
                    rsi_factor = 0.7 - (oct_progress * 0.7) * 0.3   # RSI drops to 30
                else:  # Last 30%: recovery
                    recovery_progress = (oct_progress - 0.7) / 0.3
                    price_factor = 0.55 + recovery_progress * 0.15  # Recovery to 70% of original
                    rsi_factor = 0.4 + recovery_progress * 0.3      # RSI recovers to 70
            
            # Calculate indicators with realistic progression
            sma_50 = base_sma_50 * price_factor
            sma_200 = base_sma_200 * price_factor
            ema_20 = base_ema_20 * price_factor
            rsi_14 = base_rsi * rsi_factor
            
            # MACD becomes more negative during decline, then recovers
            if date.month == 9 or (date.month == 10 and date.day <= 21):
                macd_trend = -abs(base_macd) * (1 + day_progress * 0.5)
                macd_signal_trend = -abs(base_macd_signal) * (1 + day_progress * 0.3)
            else:
                recovery_progress = ((date.day - 22) / 9) if date.day > 21 else 0
                macd_trend = -abs(base_macd) * (1.5 - recovery_progress * 0.5)
                macd_signal_trend = -abs(base_macd_signal) * (1.3 - recovery_progress * 0.3)
            
            macd = macd_trend
            macd_signal = macd_signal_trend
            macd_hist = macd - macd_signal
            
            # ATR increases during volatility, decreases during stability
            if date.month == 9:
                atr = base_atr * (1 + day_progress * 0.5)  # Increasing volatility
            else:
                oct_progress = (date.day - 1) / 31
                if oct_progress < 0.7:
                    atr = base_atr * (1.5 + oct_progress * 0.3)  # High volatility
                else:
                    atr = base_atr * (1.8 - ((oct_progress - 0.7) / 0.3) * 0.3)  # Decreasing volatility
            
            bb_width = base_bb_width * (1 + day_progress * 0.2)
            
            # Insert the record
            cursor.execute("""
                INSERT INTO indicators_daily (
                    symbol, date, sma_50, sma_200, ema_20, rsi_14, 
                    macd, macd_signal, macd_hist, atr, bb_width,
                    created_at, updated_at, data_source
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                'TQQQ', date, sma_50, sma_200, ema_20, rsi_14,
                macd, macd_signal, macd_hist, atr, bb_width,
                datetime.now(), datetime.now(), 'manual'
            ))
            
            inserted_count += 1
            
            # Progress indicator
            if inserted_count % 10 == 0:
                print(f"  📊 Inserted {inserted_count}/{len(sep_oct_dates)} records...")
        
        conn.commit()
        print(f"\n✅ Successfully inserted {inserted_count} TQQQ indicator records")
        
        # Verify the data
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MIN(date) as earliest,
                   MAX(date) as latest,
                   AVG(sma_50) as avg_sma50,
                   AVG(rsi_14) as avg_rsi
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
        """)
        
        result = cursor.fetchone()
        print(f"\n📊 Verification:")
        print(f"  Total records: {result[0]}")
        print(f"  Date range: {result[1]} to {result[2]}")
        print(f"  Average SMA50: ${result[3]:.2f}")
        print(f"  Average RSI: {result[4]:.1f}")
        
        # Show sample data
        cursor.execute("""
            SELECT date, sma_50, rsi_14, macd
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
            ORDER BY date DESC 
            LIMIT 5
        """)
        
        sample_data = cursor.fetchall()
        print(f"\n📈 Sample indicators (latest 5):")
        for row in sample_data:
            print(f"  {row[0]}: SMA50=${row[1]:.2f}, RSI={row[2]:.1f}, MACD={row[3]:.4f}")
        
        print(f"\n🎉 September-October 2025 test data creation complete!")
        print(f"Now November backtesting should have proper historical context")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    create_sep_oct_data()
