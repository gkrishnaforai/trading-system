#!/usr/bin/env python3
"""
Find SELL Signal Examples in 2025
Search for dates where we should generate SELL signals
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime

# Import unified engine
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def find_sell_signal_candidates():
    """Find dates where we should get SELL signals"""
    
    print("🔍 FINDING SELL SIGNAL CANDIDATES IN 2025")
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
        print()
        
        # Initialize unified engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Search for SELL signal candidates
        sell_candidates = []
        
        print(f"🔍 SEARCHING FOR SELL SIGNAL CANDIDATES:")
        print("-" * 50)
        
        for idx, row in df.iterrows():
            date = row['date']
            rsi = row['rsi']
            
            # Skip first few days for volatility calculation
            pos = df.index.get_loc(idx)
            if pos < 10:
                continue
            
            try:
                # Create market conditions
                recent_close = df.iloc[pos-2]['close']
                recent_change = (row['close'] - recent_close) / recent_close
                
                start_idx = max(0, pos - 19)
                volatility_data = df.iloc[start_idx:pos+1]['close'].pct_change().dropna()
                volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
                
                conditions = MarketConditions(
                    rsi=row['rsi'],
                    sma_20=row['ema_20'],
                    sma_50=row['sma_50'],
                    ema_20=row['ema_20'],
                    current_price=row['close'],
                    recent_change=recent_change,
                    macd=row['macd'],
                    macd_signal=row['macd_signal'],
                    volatility=volatility
                )
                
                # Check for SELL conditions manually
                sell_reasons = []
                
                # Mean Reversion SELL conditions
                is_overbought = conditions.rsi > 70
                is_recently_up = conditions.recent_change > 0.02
                
                if is_overbought and is_recently_up:
                    sell_reasons.append("Mean reversion: Overbought with recent strength")
                
                # Trend Continuation SELL conditions
                if conditions.current_price < conditions.sma_50:
                    sell_reasons.append("Trend continuation: Trend failure")
                
                if conditions.rsi > 70:
                    sell_reasons.append("Trend continuation: Overbought")
                
                # Breakout SELL conditions
                if conditions.rsi < 55:
                    sell_reasons.append("Breakout: Failed breakout")
                
                # Volatility Expansion SELL conditions
                if conditions.recent_change < -0.03:
                    sell_reasons.append("Volatility expansion: Sharp decline")
                
                if conditions.rsi > 70:
                    sell_reasons.append("Volatility expansion: Overbought risk")
                
                # If we have SELL reasons, check what engine actually generates
                if sell_reasons:
                    signal_result = engine.generate_signal(conditions)
                    
                    if signal_result.signal.value == "sell":
                        sell_candidates.append({
                            'date': date,
                            'rsi': rsi,
                            'price': row['close'],
                            'recent_change': recent_change,
                            'volatility': volatility,
                            'regime': signal_result.metadata.get('regime', 'unknown'),
                            'confidence': signal_result.confidence,
                            'reasoning': signal_result.reasoning,
                            'expected_reasons': sell_reasons
                        })
                        
                        print(f"🔴 FOUND SELL: {date.strftime('%Y-%m-%d')}")
                        print(f"   RSI: {rsi:.1f}, Price: ${row['close']:.2f}")
                        print(f"   Recent Change: {recent_change:+.2%}")
                        print(f"   Regime: {signal_result.metadata.get('regime', 'unknown')}")
                        print(f"   Confidence: {signal_result.confidence:.2f}")
                        print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
                        print(f"   Expected Reasons: {', '.join(sell_reasons)}")
                        print()
                        
                        if len(sell_candidates) >= 10:  # Get first 10 examples
                            break
                    else:
                        # Engine didn't generate SELL when we expected it
                        print(f"⚠️  MISSED SELL: {date.strftime('%Y-%m-%d')}")
                        print(f"   RSI: {rsi:.1f}, Price: ${row['close']:.2f}")
                        print(f"   Expected: {', '.join(sell_reasons)}")
                        print(f"   Actual: {signal_result.signal.value.upper()} ({signal_result.confidence:.2f})")
                        print()
                
            except Exception as e:
                continue
        
        print(f"📊 SELL SIGNAL ANALYSIS:")
        print("-" * 40)
        print(f"  Found {len(sell_candidates)} actual SELL signals")
        
        if sell_candidates:
            print(f"  Sample SELL signals:")
            for i, candidate in enumerate(sell_candidates[:5]):
                print(f"    {i+1}. {candidate['date'].strftime('%Y-%m-%d')}: RSI {candidate['rsi']:.1f}, {candidate['regime']}")
        
        # Also check for high RSI days that should be SELL
        print()
        print(f"🔍 HIGH RSI DAYS (Should be SELL):")
        print("-" * 40)
        
        high_rsi_days = df[df['rsi'] > 68].head(10)
        
        for idx, row in high_rsi_days.iterrows():
            date = row['date']
            rsi = row['rsi']
            
            pos = df.index.get_loc(idx)
            if pos >= 10:
                try:
                    recent_close = df.iloc[pos-2]['close']
                    recent_change = (row['close'] - recent_close) / recent_close
                    
                    start_idx = max(0, pos - 19)
                    volatility_data = df.iloc[start_idx:pos+1]['close'].pct_change().dropna()
                    volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
                    
                    conditions = MarketConditions(
                        rsi=row['rsi'],
                        sma_20=row['ema_20'],
                        sma_50=row['sma_50'],
                        ema_20=row['ema_20'],
                        current_price=row['close'],
                        recent_change=recent_change,
                        macd=row['macd'],
                        macd_signal=row['macd_signal'],
                        volatility=volatility
                    )
                    
                    signal_result = engine.generate_signal(conditions)
                    
                    print(f"  {date.strftime('%Y-%m-%d')}: RSI {rsi:.1f} -> {signal_result.signal.value.upper()} (conf: {signal_result.confidence:.2f})")
                    
                except Exception as e:
                    print(f"  {date.strftime('%Y-%m-%d')}: RSI {rsi:.1f} -> ERROR: {e}")
        
        conn.close()
        
        return sell_candidates
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    find_sell_signal_candidates()
