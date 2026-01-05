#!/usr/bin/env python3
"""
Load 1 year of TQQQ historical data and indicators for comprehensive backtesting
"""

import psycopg2
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def load_one_year_historical_data():
    """Load 1 year of TQQQ historical data and calculate indicators"""
    
    print("📈 Loading 1 Year of TQQQ Historical Data")
    print("=" * 60)
    
    # Database connection
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Download 1 year of TQQQ data
        print("📥 Downloading TQQQ data from Yahoo Finance...")
        import yfinance as yf
        
        tqqq = yf.Ticker("TQQQ")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        tqqq_data = tqqq.history(start=start_date, end=end_date)
        
        print(f"✅ Downloaded {len(tqqq_data)} days of TQQQ data")
        print(f"📅 Date range: {tqqq_data.index[0].date()} to {tqqq_data.index[-1].date()}")
        
        # Step 1: Load raw price data
        print("\n💾 Loading raw price data...")
        
        # Clear existing TQQQ data for the period
        cursor.execute("""
            DELETE FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= %s 
            AND date <= %s
        """, (start_date.date(), end_date.date()))
        
        # Insert raw price data
        price_count = 0
        for date, row in tqqq_data.iterrows():
            cursor.execute("""
                INSERT INTO raw_market_data_daily (
                    symbol, date, open, high, low, close, volume, 
                    adjusted_close, data_source, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                'TQQQ', date.date(), 
                float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']),
                int(row.get('Volume', 0)), float(row['Close']),
                'yahoo_finance', datetime.now()
            ))
            price_count += 1
        
        conn.commit()
        print(f"✅ Loaded {price_count} price records")
        
        # Step 2: Calculate and load indicators
        print("\n📈 Calculating technical indicators...")
        
        # Convert to DataFrame for indicator calculation
        price_records = []
        for date, row in tqqq_data.iterrows():
            price_records.append({
                'date': date.date(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row.get('Volume', 0))
            })
        
        df = pd.DataFrame(price_records)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Calculate technical indicators
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()
        df['sma_200'] = df['close'].rolling(window=200, min_periods=1).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # RSI
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
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(window=14, min_periods=1).mean()
        
        # Bollinger Bands
        df['bb_middle'] = df['sma_20']
        bb_std = df['close'].rolling(window=20, min_periods=1).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # Fill NaN values
        df = df.fillna(method='ffill').fillna(method='bfill')
        
        print("💾 Loading calculated indicators...")
        
        # Clear existing indicators for the period
        cursor.execute("""
            DELETE FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= %s 
            AND date <= %s
        """, (start_date.date(), end_date.date()))
        
        # Insert indicators
        indicator_count = 0
        for date, row in df.iterrows():
            if not pd.isna(row['sma_20']) and not pd.isna(row['sma_50']):
                cursor.execute("""
                    INSERT INTO indicators_daily (
                        symbol, date, sma_20, sma_50, sma_200, ema_20, 
                        rsi_14, macd, macd_signal, macd_hist, atr, bb_width,
                        created_at, updated_at, data_source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    'TQQQ', date.date(), 
                    float(row['sma_20']), float(row['sma_50']), float(row['sma_200']), float(row['ema_20']),
                    float(row['rsi_14']), float(row['macd']), float(row['macd_signal']), 
                    float(row['macd_hist']), float(row['atr']), float(row['bb_width']),
                    datetime.now(), datetime.now(), 'calculated'
                ))
                indicator_count += 1
        
        conn.commit()
        print(f"✅ Loaded {indicator_count} indicator records")
        
        # Verification
        print("\n📊 Verification Summary:")
        
        # Price data verification
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MIN(date) as earliest,
                   MAX(date) as latest,
                   AVG(close) as avg_close,
                   MIN(close) as min_close,
                   MAX(close) as max_close
            FROM raw_market_data_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= %s 
            AND date <= %s
        """, (start_date.date(), end_date.date()))
        
        price_result = cursor.fetchone()
        if price_result:
            print(f"  📈 Price Data:")
            print(f"    Records: {price_result[0]}")
            print(f"    Range: {price_result[1]} to {price_result[2]}")
            print(f"    Price: ${price_result[3]:.2f} - ${price_result[4]:.2f} (avg: ${price_result[5]:.2f})")
        
        # Indicator verification
        cursor.execute("""
            SELECT COUNT(*) as total,
                   MIN(date) as earliest,
                   MAX(date) as latest,
                   AVG(sma_50) as avg_sma50,
                   AVG(rsi_14) as avg_rsi,
                   AVG(atr) as avg_atr
            FROM indicators_daily 
            WHERE symbol = 'TQQQ' 
            AND date >= %s 
            AND date <= %s
        """, (start_date.date(), end_date.date()))
        
        indicator_result = cursor.fetchone()
        if indicator_result:
            print(f"  📊 Indicators:")
            print(f"    Records: {indicator_result[0]}")
            print(f"    Range: {indicator_result[1]} to {indicator_result[2]}")
            print(f"    SMA50: ${indicator_result[3]:.2f}")
            print(f"    RSI: {indicator_result[4]:.1f}")
            print(f"    ATR: ${indicator_result[5]:.2f}")
        
        # Sample recent data
        cursor.execute("""
            SELECT date, close, sma_50, rsi_14, macd
            FROM indicators_daily i
            JOIN raw_market_data_daily p ON i.date = p.date AND i.symbol = p.symbol
            WHERE i.symbol = 'TQQQ' 
            ORDER BY i.date DESC 
            LIMIT 5
        """)
        
        sample_data = cursor.fetchall()
        print(f"\n📈 Recent Data (last 5 days):")
        for row in sample_data:
            print(f"  {row[0]}: Close=${row[1]:.2f}, SMA50=${row[2]:.2f}, RSI={row[3]:.1f}")
        
        # Coverage analysis
        total_days = (end_date.date() - start_date.date()).days
        trading_days = indicator_count if indicator_count else 0
        coverage = (trading_days / total_days) * 100 if total_days > 0 else 0
        
        print(f"\n📊 Coverage Analysis:")
        print(f"  Total period: {total_days} days")
        print(f"  Trading days: {trading_days}")
        print(f"  Coverage: {coverage:.1f}%")
        
        print(f"\n🎉 1 Year Historical Data Loading Complete!")
        print(f"✅ Ready for comprehensive backtesting across all market conditions")
        print(f"📅 Data covers: {start_date.date()} to {end_date.date()}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    load_one_year_historical_data()
