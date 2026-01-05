#!/usr/bin/env python3
"""
Insert test data for December 31, 2025 to enable backtesting
"""

import psycopg2
import os
from datetime import datetime

def insert_test_data():
    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        print("🔧 Inserting Test Data for December 31, 2025")
        print("=" * 50)
        
        # Get the latest TQQQ indicators data as a template
        cursor.execute("""
            SELECT sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, macd_hist, 
                   atr, bb_width, signal, confidence_score
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            ORDER BY date DESC 
            LIMIT 1
        """)
        
        template_data = cursor.fetchone()
        
        if template_data:
            # Insert test data for December 31, 2025 with slight variations
            test_data = {
                'sma_50': template_data[0] * 0.98,  # Slightly lower
                'sma_200': template_data[1] * 0.97,  # Slightly lower
                'ema_20': template_data[2] * 0.98,   # Slightly lower
                'rsi_14': template_data[3] * 1.1,    # Slightly higher (more overbought)
                'macd': template_data[4] * 0.9,       # Slightly lower
                'macd_signal': template_data[5] * 0.95,  # Slightly lower
                'macd_hist': template_data[6] * 0.8,   # More negative
                'atr': template_data[7],
                'bb_width': template_data[8],
                'signal': 'sell',  # Different signal
                'confidence_score': 0.7  # Higher confidence
            }
            
            # Insert multiple records for December 31, 2025
            for i in range(5):
                cursor.execute("""
                    INSERT INTO indicators_daily (
                        symbol, date, sma_50, sma_200, ema_20, rsi_14, 
                        macd, macd_signal, macd_hist, atr, bb_width,
                        signal, confidence_score, created_at, updated_at,
                        indicator_name, data_source
                    ) VALUES (
                        'TQQQ', '2025-12-31', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, NOW(), NOW(), 'test_backtest', 'manual'
                    )
                """, (
                    test_data['sma_50'],
                    test_data['sma_200'], 
                    test_data['ema_20'],
                    test_data['rsi_14'],
                    test_data['macd'],
                    test_data['macd_signal'],
                    test_data['macd_hist'],
                    test_data['atr'],
                    test_data['bb_width'],
                    test_data['signal'],
                    test_data['confidence_score']
                ))
            
            conn.commit()
            print(f"✅ Inserted 5 test records for TQQQ on 2025-12-31")
            print(f"   SMA50: {test_data['sma_50']:.2f}")
            print(f"   RSI: {test_data['rsi_14']:.2f}")
            print(f"   Signal: {test_data['signal']}")
            print(f"   Confidence: {test_data['confidence_score']}")
            
        else:
            print("❌ No template data found for TQQQ")
        
        # Also insert data for December 30 and 29 for better backtesting
        dates = ['2025-12-30', '2025-12-29', '2025-12-26', '2025-12-24']
        
        for date in dates:
            # Create variations for each date
            variation = 1.0 - (0.02 * (len(dates) - dates.index(date)))  # Progressive decrease
            
            cursor.execute("""
                INSERT INTO indicators_daily (
                    symbol, date, sma_50, sma_200, ema_20, rsi_14, 
                    macd, macd_signal, macd_hist, atr, bb_width,
                    signal, confidence_score, created_at, updated_at,
                    indicator_name, data_source
                ) VALUES (
                    'TQQQ', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, NOW(), NOW(), 'test_backtest', 'manual'
                )
            """, (
                template_data[0] * variation,
                template_data[1] * variation,
                template_data[2] * variation,
                template_data[3] * (1.1 + len(dates) - dates.index(date)),  # RSI variation
                template_data[4] * variation,
                template_data[5] * variation,
                template_data[6] * variation,
                template_data[7],
                template_data[8],
                'buy' if date == '2025-12-26' else 'hold',  # Mix of signals
                0.6 + (0.1 * (len(dates) - dates.index(date)))  # Varying confidence
            ))
        
        conn.commit()
        print(f"✅ Added test data for dates: {', '.join(dates)}")
        
        # Verify the data
        cursor.execute("""
            SELECT date, COUNT(*) as count, AVG(sma_50) as avg_sma, AVG(rsi_14) as avg_rsi
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' AND date >= '2025-12-24'
            GROUP BY date
            ORDER BY date
        """)
        
        results = cursor.fetchall()
        print("\n📊 Verification - TQQQ Test Data:")
        for date, count, avg_sma, avg_rsi in results:
            print(f"  {date}: {count} records, SMA50={avg_sma:.2f}, RSI={avg_rsi:.2f}")
        
        conn.close()
        print("\n🎯 Test data ready! Now you can backtest December 24-31, 2025")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    insert_test_data()
