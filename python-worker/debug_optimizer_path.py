#!/usr/bin/env python3
"""
Debug Optimizer Signal Generation - Exact Path
Trace exactly what the optimizer is doing
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
from specialized_engines import CompositeSwingEngine
from quality_optimizer import QualityBasedOptimizer

def debug_optimizer_path():
    """Debug the exact optimizer path"""
    
    print("🔍 DEBUG OPTIMIZER SIGNAL GENERATION PATH")
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
        print(f"  Max Volatility: {config.max_volatility}")
        print()
        
        # Initialize optimizer (same as test)
        optimizer = QualityBasedOptimizer(df)
        
        # Initialize engine (same as optimizer)
        engine = CompositeSwingEngine(config, df)
        
        # Test the exact same method as optimizer
        print(f"🎯 Testing Optimizer Signal Generation:")
        print("-" * 50)
        
        # Use the exact same loop as optimizer.evaluate_config_quality
        buy_count = 0
        sell_count = 0
        hold_count = 0
        signal_results = []
        
        # Exact same range as optimizer
        for i in range(10, len(df) - 7):  # Need forward data for validation
            try:
                current_date = df.iloc[i]['date']
                conditions = optimizer._create_market_conditions(i)
                
                # Debug: Show conditions for low RSI days
                if conditions.rsi < 45:
                    print(f"🔍 Day {i} ({current_date.strftime('%Y-%m-%d')}): RSI {conditions.rsi:.1f}")
                    print(f"   Recent Change: {conditions.recent_change:+.2%}")
                    print(f"   SMA20: {conditions.sma_20:.2f}, SMA50: {conditions.sma_50:.2f}")
                    print(f"   Is Uptrend: {conditions.sma_20 > conditions.sma_50 and conditions.current_price > conditions.sma_20}")
                
                signal_result = engine.generate_composite_signal(conditions, "TQQQ", current_date)
                signal_results.append((current_date, signal_result, conditions))
                
                # Count signals
                if signal_result.signal == SignalType.BUY:
                    buy_count += 1
                    if conditions.rsi < 45:
                        print(f"   🟢 BUY! Confidence: {signal_result.confidence:.2f}")
                        print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
                elif signal_result.signal == SignalType.SELL:
                    sell_count += 1
                    if conditions.rsi < 45:
                        print(f"   🔴 SELL! Confidence: {signal_result.confidence:.2f}")
                else:
                    hold_count += 1
                    if conditions.rsi < 45:
                        print(f"   ⚪ HOLD! Confidence: {signal_result.confidence:.2f}")
                        print(f"   Reasoning: {signal_result.reasoning[0] if signal_result.reasoning else 'No reasoning'}")
                
                if conditions.rsi < 45:
                    print()
                    
            except Exception as e:
                print(f"   🚨 Error at day {i}: {e}")
                continue
        
        print(f"📊 OPTIMIZER SIGNAL GENERATION SUMMARY:")
        print("-" * 40)
        print(f"  BUY Signals: {buy_count}")
        print(f"  SELL Signals: {sell_count}")
        print(f"  HOLD Signals: {hold_count}")
        print(f"  Total Tested: {buy_count + sell_count + hold_count}")
        print()
        
        # Check what the optimizer actually returns
        print(f"🎯 TESTING OPTIMIZER.evaluate_config_quality():")
        print("-" * 50)
        
        result = optimizer.evaluate_config_quality(config)
        
        print(f"  Optimizer Result:")
        print(f"    BUY Rate: {result.buy_rate:.1f}%")
        print(f"    BUY Count: {int(result.buy_rate * (buy_count + sell_count + hold_count) / 100)}")
        print(f"    Overall Score: {result.overall_score:.1f}")
        print(f"    Meets Objectives: {result.meets_objectives}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_optimizer_path()
