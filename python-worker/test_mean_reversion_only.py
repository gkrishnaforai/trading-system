#!/usr/bin/env python3
"""
Simple Test - Just MeanReversion Engine
Test if the basic engine is working
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append('/app/enhancements')

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime

# Import components
from app.signal_engines.signal_calculator_core import (
    SignalType, MarketConditions, SignalConfig, SignalResult
)
from specialized_engines import MeanReversionEngine

def test_mean_reversion_only():
    """Test just the MeanReversion engine"""
    
    print("🔍 TESTING MEAN REVERSION ENGINE ONLY")
    print("=" * 50)
    
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
        print()
        
        # Use the exact same configuration as the optimizer
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=34,
            rsi_mildly_oversold=41,
            max_volatility=7.5
        )
        
        print(f"⚙️ Using Configuration:")
        print(f"  RSI Oversold: {config.rsi_oversold}")
        print(f"  RSI Moderate: {config.rsi_moderately_oversold}")
        print(f"  RSI Mild: {config.rsi_mildly_oversold}")
        print()
        
        # Initialize just the MeanReversion engine
        engine = MeanReversionEngine(config)
        
        # Test on low RSI days
        low_rsi_days = df[df['rsi'] < 45].head(10)
        
        print(f"🎯 Testing MeanReversion Engine on Low RSI Days:")
        print("-" * 50)
        
        buy_count = 0
        sell_count = 0
        hold_count = 0
        
        for idx, row in low_rsi_days.iterrows():
            date = row['date']
            rsi = row['rsi']
            
            # Get position in dataframe
            pos = df.index.get_loc(idx)
            
            if pos < 2:
                continue
            
            # Create market conditions
            current = df.iloc[pos]
            recent_close = df.iloc[pos-2]['close']
            recent_change = (current['close'] - recent_close) / recent_close
            
            start_idx = max(0, pos - 19)
            volatility_data = df.iloc[start_idx:pos+1]['close'].pct_change().dropna()
            volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
            
            conditions = MarketConditions(
                rsi=current['rsi'],
                sma_20=current['ema_20'],
                sma_50=current['sma_50'],
                ema_20=current['ema_20'],
                current_price=current['close'],
                recent_change=recent_change,
                macd=current['macd'],
                macd_signal=current['macd_signal'],
                volatility=volatility
            )
            
            print(f"🔍 {date.strftime('%Y-%m-%d')}: RSI {rsi:.1f}")
            print(f"   Recent Change: {recent_change:+.2%}")
            print(f"   SMA20: {conditions.sma_20:.2f}, SMA50: {conditions.sma_50:.2f}")
            print(f"   Is Uptrend: {conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20}")
            
            # Step 1: Check if engine should generate signal
            should_generate = engine.should_generate_signal(conditions)
            print(f"   Should Generate: {should_generate}")
            
            if should_generate:
                # Step 2: Generate signal
                signal_result = engine.generate_signal_logic(conditions)
                
                # Count signals
                if signal_result.signal == SignalType.BUY:
                    buy_count += 1
                    signal_icon = "🟢"
                elif signal_result.signal == SignalType.SELL:
                    sell_count += 1
                    signal_icon = "🔴"
                else:
                    hold_count += 1
                    signal_icon = "⚪"
                
                print(f"   {signal_icon} SIGNAL: {signal_result.signal.value.upper()} (confidence: {signal_result.confidence:.2f})")
                print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
            else:
                print(f"   ❌ REJECTED by should_generate_signal()")
            
            print()
        
        print(f"📊 MEAN REVERSION ENGINE SUMMARY:")
        print("-" * 40)
        print(f"  BUY Signals: {buy_count}")
        print(f"  SELL Signals: {sell_count}")
        print(f"  HOLD Signals: {hold_count}")
        print(f"  Total Tested: {buy_count + sell_count + hold_count}")
        print()
        
        # Test on all days to see overall pattern
        print(f"🎯 TESTING ON ALL DAYS (Sample):")
        print("-" * 40)
        
        total_buy = 0
        total_sell = 0
        total_hold = 0
        total_rejected = 0
        
        for i in range(10, min(50, len(df))):  # Test first 50 days
            try:
                current = df.iloc[i]
                recent_close = df.iloc[i-2]['close']
                recent_change = (current['close'] - recent_close) / recent_close
                
                start_idx = max(0, i - 19)
                volatility_data = df.iloc[start_idx:i+1]['close'].pct_change().dropna()
                volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
                
                conditions = MarketConditions(
                    rsi=current['rsi'],
                    sma_20=current['ema_20'],
                    sma_50=current['sma_50'],
                    ema_20=current['ema_20'],
                    current_price=current['close'],
                    recent_change=recent_change,
                    macd=current['macd'],
                    macd_signal=current['macd_signal'],
                    volatility=volatility
                )
                
                should_generate = engine.should_generate_signal(conditions)
                
                if should_generate:
                    signal_result = engine.generate_signal_logic(conditions)
                    if signal_result.signal == SignalType.BUY:
                        total_buy += 1
                    elif signal_result.signal == SignalType.SELL:
                        total_sell += 1
                    else:
                        total_hold += 1
                else:
                    total_rejected += 1
                    
            except Exception as e:
                continue
        
        print(f"  Total BUY: {total_buy}")
        print(f"  Total SELL: {total_sell}")
        print(f"  Total HOLD: {total_hold}")
        print(f"  Total REJECTED: {total_rejected}")
        print(f"  BUY Rate: {(total_buy / (total_buy + total_sell + total_hold) * 100) if (total_buy + total_sell + total_hold) > 0 else 0:.1f}%")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mean_reversion_only()
