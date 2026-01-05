#!/usr/bin/env python3
"""
Calculate indicators for TQQQ September-October 2025 data
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
sys.path.append('/app')

def calculate_indicators_for_sep_oct():
    """Calculate technical indicators for TQQQ Sep-Oct 2025 data"""
    
    print("📈 Calculating Indicators for TQQQ Sep-Oct 2025")
    print("=" * 60)
    
    try:
        from app.database import db
        
        # Get TQQQ price data for Sep-Oct 2025
        print("📊 Fetching TQQQ price data...")
        query = """
            SELECT date, open, high, low, close, volume
            FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
            ORDER BY date ASC
        """
        
        price_data = db.execute_query(query)
        
        if not price_data:
            print("❌ No price data found for Sep-Oct 2025")
            return
        
        print(f"✅ Found {len(price_data)} price records")
        
        # Convert to DataFrame
        df = pd.DataFrame(price_data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        print(f"📅 Date range: {df.index[0].date()} to {df.index[-1].date()}")
        print(f"💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        
        # Calculate technical indicators
        print("📈 Calculating technical indicators...")
        
        # Simple Moving Averages
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()
        df['sma_200'] = df['close'].rolling(window=200, min_periods=1).mean()
        
        # Exponential Moving Average
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # RSI (Relative Strength Index)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        
        # Fill NaN values with forward fill then backward fill
        df = df.fillna(method='ffill').fillna(method='bfill')
        
        print(f"✅ Indicators calculated successfully")
        
        # Clear existing indicators for Sep-Oct 2025
        print("🗑️ Clearing existing indicators for Sep-Oct 2025...")
        db.execute_update("""
            DELETE FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
        """)
        
        # Insert calculated indicators
        print("💾 Inserting calculated indicators...")
        
        indicators_inserted = 0
        for date, row in df.iterrows():
            # Only insert if we have valid data
            if not pd.isna(row['sma_20']) and not pd.isna(row['sma_50']):
                # Insert SMA indicators
                sma_record = {
                    'symbol': 'TQQQ',
                    'date': date.date(),
                    'indicator_name': 'sma_20',
                    'sma_20': float(row['sma_20']),
                    'sma_50': float(row['sma_50']),
                    'sma_200': float(row['sma_200']) if not pd.isna(row['sma_200']) else None,
                    'ema_20': float(row['ema_20']),
                    'rsi_14': float(row['rsi_14']),
                    'macd': float(row['macd']),
                    'macd_signal': float(row['macd_signal']),
                    'created_at': datetime.now(),
                    'updated_at': datetime.now(),
                    'data_source': 'calculated'
                }
                
                insert_query = """
                    INSERT INTO indicators_daily (
                        symbol, date, indicator_name, sma_20, sma_50, sma_200, ema_20, 
                        rsi_14, macd, macd_signal, created_at, updated_at, data_source
                    ) VALUES (
                        :symbol, :date, :indicator_name, :sma_20, :sma_50, :sma_200, :ema_20,
                        :rsi_14, :macd, :macd_signal, :created_at, :updated_at, :data_source
                    )
                """
                
                db.execute_update(insert_query, sma_record)
                indicators_inserted += 1
        
        print(f"✅ Successfully inserted {indicators_inserted} indicator records")
        
        # Verify the indicators
        verify_query = """
            SELECT COUNT(*) as total,
                   MIN(date) as earliest,
                   MAX(date) as latest,
                   AVG(sma_50) as avg_sma50,
                   AVG(rsi_14) as avg_rsi
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
        """
        
        result = db.execute_query(verify_query)
        if result:
            row = result[0]
            print(f"📊 Indicator Verification:")
            print(f"  Total records: {row['total']}")
            print(f"  Date range: {row['earliest']} to {row['latest']}")
            print(f"  Average SMA50: ${row['avg_sma50']:.2f}")
            print(f"  Average RSI: {row['avg_rsi']:.1f}")
        
        # Show sample indicators
        sample_query = """
            SELECT date, sma_20, sma_50, rsi_14, macd, macd_signal
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= '2025-09-01' 
            AND date <= '2025-10-31'
            ORDER BY date DESC 
            LIMIT 5
        """
        
        sample_data = db.execute_query(sample_query)
        print(f"\n📈 Sample indicators (latest 5):")
        for row in sample_data:
            print(f"  {row['date']}: SMA50=${row['sma_50']:.2f}, RSI={row['rsi_14']:.1f}")
        
        # Check total indicators availability
        total_query = """
            SELECT COUNT(*) as total,
                   MIN(date) as earliest,
                   MAX(date) as latest
            FROM indicators_daily 
            WHERE symbol = 'TQQQ'
        """
        
        total_result = db.execute_query(total_query)
        if total_result:
            total_row = total_result[0]
            print(f"\n📊 Total TQQQ indicators in database:")
            print(f"  Total records: {total_row['total']}")
            print(f"  Full date range: {total_row['earliest']} to {total_row['latest']}")
        
        print(f"\n🎉 Indicator calculation complete!")
        print(f"Now November backtesting should have proper indicators")
        
    except Exception as e:
        print(f"❌ Error calculating indicators: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    calculate_indicators_for_sep_oct()
