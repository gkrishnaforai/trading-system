#!/usr/bin/env python3
"""
Check RSI Distribution in 2025 TQQQ Data
How many days had RSI < 45 and RSI < 38?
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime

def check_rsi_distribution():
    """Check RSI distribution in 2025 TQQQ data"""
    
    print("📊 RSI Distribution Analysis - 2025 TQQQ Data")
    print("=" * 60)
    
    # Load data
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = 'TQQQ' 
            AND i.date >= '2025-01-01' 
            AND i.date <= '2025-12-31'
            ORDER BY i.date
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            print("❌ No 2025 data found")
            return
        
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
        ])
        df['date'] = pd.to_datetime(df['date'])
        
        print(f"✅ Loaded {len(df)} records from 2025")
        print(f"📅 Date range: {df['date'].min()} to {df['date'].max()}")
        print()
        
        # RSI Analysis
        rsi_45_count = len(df[df['rsi'] < 45])
        rsi_38_count = len(df[df['rsi'] < 38])
        rsi_34_count = len(df[df['rsi'] < 34])
        
        rsi_45_pct = (rsi_45_count / len(df)) * 100
        rsi_38_pct = (rsi_38_count / len(df)) * 100
        rsi_34_pct = (rsi_34_count / len(df)) * 100
        
        print("🎯 RSI THRESHOLD ANALYSIS:")
        print("-" * 40)
        print(f"  Days with RSI < 45: {rsi_45_count} ({rsi_45_pct:.1f}%)")
        print(f"  Days with RSI < 38: {rsi_38_count} ({rsi_38_pct:.1f}%)")
        print(f"  Days with RSI < 34: {rsi_34_count} ({rsi_34_pct:.1f}%)")
        print()
        
        # RSI Range Analysis
        print("📈 RSI RANGE DISTRIBUTION:")
        print("-" * 40)
        rsi_ranges = [
            (0, 20, "Extremely Oversold"),
            (20, 30, "Very Oversold"),
            (30, 40, "Oversold"),
            (40, 50, "Neutral-Low"),
            (50, 60, "Neutral-High"),
            (60, 70, "Overbought"),
            (70, 100, "Very Overbought")
        ]
        
        for min_rsi, max_rsi, label in rsi_ranges:
            count = len(df[(df['rsi'] >= min_rsi) & (df['rsi'] < max_rsi)])
            pct = (count / len(df)) * 100
            print(f"  RSI {min_rsi}-{max_rsi}: {count:3d} days ({pct:5.1f}%) - {label}")
        
        print()
        
        # Specific dates with low RSI
        print("📅 SPECIFIC DATES WITH LOW RSI:")
        print("-" * 40)
        low_rsi_days = df[df['rsi'] < 45].sort_values('rsi').head(10)
        
        for _, row in low_rsi_days.iterrows():
            print(f"  {row['date'].strftime('%Y-%m-%d')}: RSI {row['rsi']:.1f}, Price ${row['close']:.2f}")
        
        print()
        print("📅 SPECIFIC DATES WITH VERY LOW RSI (< 38):")
        print("-" * 40)
        very_low_rsi_days = df[df['rsi'] < 38].sort_values('rsi').head(10)
        
        if len(very_low_rsi_days) == 0:
            print("  ❌ No days with RSI < 38 in 2025!")
        else:
            for _, row in very_low_rsi_days.iterrows():
                print(f"  {row['date'].strftime('%Y-%m-%d')}: RSI {row['rsi']:.1f}, Price ${row['close']:.2f}")
        
        print()
        
        # Trend Analysis for low RSI days
        print("📊 TREND ANALYSIS FOR LOW RSI DAYS:")
        print("-" * 40)
        low_rsi_df = df[df['rsi'] < 45].copy()
        
        if len(low_rsi_df) > 0:
            # Calculate trend for low RSI days
            low_rsi_df['is_uptrend'] = (low_rsi_df['ema_20'] > low_rsi_df['sma_50']) & (low_rsi_df['close'] > low_rsi_df['ema_20'])
            low_rsi_df['is_downtrend'] = (low_rsi_df['ema_20'] < low_rsi_df['sma_50']) & (low_rsi_df['close'] < low_rsi_df['ema_20'])
            
            uptrend_count = len(low_rsi_df[low_rsi_df['is_uptrend']])
            downtrend_count = len(low_rsi_df[low_rsi_df['is_downtrend']])
            neutral_count = len(low_rsi_df) - uptrend_count - downtrend_count
            
            print(f"  Low RSI days in UPTREND: {uptrend_count} ({uptrend_count/len(low_rsi_df)*100:.1f}%)")
            print(f"  Low RSI days in DOWNTREND: {downtrend_count} ({downtrend_count/len(low_rsi_df)*100:.1f}%)")
            print(f"  Low RSI days NEUTRAL: {neutral_count} ({neutral_count/len(low_rsi_df)*100:.1f}%)")
        
        print()
        
        # Recent decline analysis
        print("📉 RECENT DECLINE ANALYSIS FOR LOW RSI DAYS:")
        print("-" * 40)
        
        if len(low_rsi_df) > 0:
            # Calculate recent change for low RSI days
            recent_decline_count = 0
            for idx, row in low_rsi_df.iterrows():
                # Get position in dataframe
                pos = df.index.get_loc(idx)
                if pos >= 2:
                    recent_close = df.iloc[pos-2]['close']
                    current_close = row['close']
                    recent_change = (current_close - recent_close) / recent_close
                    if recent_change < -0.02:  # -2% decline
                        recent_decline_count += 1
            
            recent_decline_pct = (recent_decline_count / len(low_rsi_df)) * 100
            print(f"  Low RSI days with -2% recent decline: {recent_decline_count} ({recent_decline_pct:.1f}%)")
        
        print()
        
        # Summary
        print("🎯 SUMMARY - BUY SIGNAL POTENTIAL:")
        print("-" * 40)
        print(f"  Total Trading Days: {len(df)}")
        print(f"  Days RSI < 45 (Oversold): {rsi_45_count} ({rsi_45_pct:.1f}%)")
        print(f"  Days RSI < 38 (Very Oversold): {rsi_38_count} ({rsi_38_pct:.1f}%)")
        
        if len(low_rsi_df) > 0:
            print(f"  Low RSI days in UPTREND: {uptrend_count} (MeanReversion would REJECT these)")
            print(f"  Low RSI days with -2% decline: {recent_decline_count}")
        
        print()
        print("💡 CONCLUSION:")
        if rsi_45_pct < 10:
            print("  ❌ RSI < 45 threshold is TOO RESTRICTIVE for TQQQ in 2025")
        if rsi_38_pct < 5:
            print("  ❌ RSI < 38 threshold is EXTREMELY RESTRICTIVE")
        if uptrend_count > rsi_45_count * 0.5:
            print("  ❌ Most low RSI days occur in uptrends (MeanReversion rejects)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_rsi_distribution()
