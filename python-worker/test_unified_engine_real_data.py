#!/usr/bin/env python3
"""
Test Unified Engine with Real 2025 Data
Compare signals with actual market movements
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append('/app/enhancements')

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import unified engine
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions
from forward_return_validation import SignalQualityValidator, ForwardReturnMetrics

def test_unified_engine_real_data():
    """Test unified engine with real 2025 data and market movements"""
    
    print("🚀 TESTING UNIFIED ENGINE WITH REAL 2025 DATA")
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
        print(f"💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        print()
        
        # Initialize unified engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Generate signals for all available data
        print(f"🎯 GENERATING SIGNALS FOR ALL 2025 DATA:")
        print("-" * 50)
        
        signals = []
        
        for idx, row in df.iterrows():
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
                
                # Generate signal
                signal_result = engine.generate_signal(conditions)
                
                # Calculate forward returns (3-day, 5-day, 7-day)
                forward_returns = {}
                if pos < len(df) - 7:
                    # 3-day return
                    future_price_3d = df.iloc[pos + 3]['close']
                    return_3d = (future_price_3d - row['close']) / row['close']
                    forward_returns['return_3d'] = return_3d
                    
                    # 5-day return
                    future_price_5d = df.iloc[pos + 5]['close']
                    return_5d = (future_price_5d - row['close']) / row['close']
                    forward_returns['return_5d'] = return_5d
                    
                    # 7-day return
                    future_price_7d = df.iloc[pos + 7]['close']
                    return_7d = (future_price_7d - row['close']) / row['close']
                    forward_returns['return_7d'] = return_7d
                    
                    # Max adverse excursion (worst drawdown)
                    future_prices = df.iloc[pos+1:pos+8]['close']
                    max_price = future_prices.max()
                    max_drawdown = (max_price - row['close']) / row['close']
                    forward_returns['max_adverse_excursion'] = abs(max_drawdown)
                    
                    # Max favorable excursion (best gain)
                    min_price = future_prices.min()
                    max_gain = (row['close'] - min_price) / row['close']
                    forward_returns['max_favorable_excursion'] = max_gain
                
                signals.append({
                    'date': row['date'],
                    'signal': signal_result.signal.value,
                    'confidence': signal_result.confidence,
                    'regime': signal_result.metadata.get('regime', 'unknown'),
                    'reasoning': signal_result.reasoning,
                    'entry_price': row['close'],
                    'rsi': row['rsi'],
                    'recent_change': recent_change,
                    'volatility': volatility,
                    **forward_returns
                })
                
            except Exception as e:
                continue
        
        # Convert to DataFrame for analysis
        signals_df = pd.DataFrame(signals)
        
        print(f"✅ Generated {len(signals_df)} signals")
        print()
        
        # Signal distribution
        print(f"📊 SIGNAL DISTRIBUTION:")
        print("-" * 30)
        signal_counts = signals_df['signal'].value_counts()
        for signal, count in signal_counts.items():
            pct = (count / len(signals_df)) * 100
            print(f"  {signal.upper()}: {count} ({pct:.1f}%)")
        
        print()
        
        # Regime distribution
        print(f"📊 REGIME DISTRIBUTION:")
        print("-" * 30)
        regime_counts = signals_df['regime'].value_counts()
        for regime, count in regime_counts.items():
            pct = (count / len(signals_df)) * 100
            print(f"  {regime}: {count} ({pct:.1f}%)")
        
        print()
        
        # Performance analysis by signal type
        print(f"📈 PERFORMANCE ANALYSIS BY SIGNAL TYPE:")
        print("-" * 50)
        
        for signal_type in ['buy', 'sell', 'hold']:
            signal_data = signals_df[signals_df['signal'] == signal_type]
            
            if len(signal_data) == 0:
                print(f"  {signal_type.upper()}: No signals")
                continue
            
            # Calculate metrics
            avg_return_3d = signal_data['return_3d'].mean()
            avg_return_5d = signal_data['return_5d'].mean()
            avg_return_7d = signal_data['return_7d'].mean()
            
            win_rate_3d = (signal_data['return_3d'] > 0).mean() * 100
            win_rate_5d = (signal_data['return_5d'] > 0).mean() * 100
            win_rate_7d = (signal_data['return_7d'] > 0).mean() * 100
            
            avg_mae = signal_data['max_adverse_excursion'].mean()
            avg_mfe = signal_data['max_favorable_excursion'].mean()
            
            print(f"  {signal_type.upper()} ({len(signal_data)} signals):")
            print(f"    Avg Return (3d): {avg_return_3d:+.2%}")
            print(f"    Avg Return (5d): {avg_return_5d:+.2%}")
            print(f"    Avg Return (7d): {avg_return_7d:+.2%}")
            print(f"    Win Rate (3d): {win_rate_3d:.1f}%")
            print(f"    Win Rate (5d): {win_rate_5d:.1f}%")
            print(f"    Win Rate (7d): {win_rate_7d:.1f}%")
            print(f"    Avg Max Adverse: {avg_mae:.2%}")
            print(f"    Avg Max Favorable: {avg_mfe:.2%}")
            print()
        
        # Performance analysis by regime
        print(f"📈 PERFORMANCE ANALYSIS BY REGIME:")
        print("-" * 50)
        
        for regime in signals_df['regime'].unique():
            regime_data = signals_df[signals_df['regime'] == regime]
            
            if len(regime_data) == 0:
                continue
            
            # Focus on BUY signals for regime analysis
            buy_signals = regime_data[regime_data['signal'] == 'buy']
            
            if len(buy_signals) == 0:
                print(f"  {regime}: No BUY signals")
                continue
            
            avg_return_5d = buy_signals['return_5d'].mean()
            win_rate_5d = (buy_signals['return_5d'] > 0).mean() * 100
            
            print(f"  {regime} BUY signals ({len(buy_signals)}):")
            print(f"    Avg Return (5d): {avg_return_5d:+.2%}")
            print(f"    Win Rate (5d): {win_rate_5d:.1f}%")
            print()
        
        # Best and worst performing signals
        print(f"🏆 BEST AND WORST PERFORMING SIGNALS:")
        print("-" * 50)
        
        # Best BUY signals
        buy_signals = signals_df[signals_df['signal'] == 'buy']
        if len(buy_signals) > 0:
            best_buy = buy_signals.loc[buy_signals['return_5d'].idxmax()]
            worst_buy = buy_signals.loc[buy_signals['return_5d'].idxmin()]
            
            print(f"  🥇 BEST BUY Signal:")
            print(f"    Date: {best_buy['date'].strftime('%Y-%m-%d')}")
            print(f"    Return (5d): {best_buy['return_5d']:+.2%}")
            print(f"    Regime: {best_buy['regime']}")
            print(f"    Confidence: {best_buy['confidence']:.2f}")
            print(f"    Entry Price: ${best_buy['entry_price']:.2f}")
            print(f"    Reasoning: {best_buy['reasoning'][0] if best_buy['reasoning'] else 'No reasoning'}")
            print()
            
            print(f"  💩 WORST BUY Signal:")
            print(f"    Date: {worst_buy['date'].strftime('%Y-%m-%d')}")
            print(f"    Return (5d): {worst_buy['return_5d']:+.2%}")
            print(f"    Regime: {worst_buy['regime']}")
            print(f"    Confidence: {worst_buy['confidence']:.2f}")
            print(f"    Entry Price: ${worst_buy['entry_price']:.2f}")
            print(f"    Reasoning: {worst_buy['reasoning'][0] if worst_buy['reasoning'] else 'No reasoning'}")
            print()
        
        # Overall statistics
        print(f"📊 OVERALL STATISTICS:")
        print("-" * 30)
        
        total_buy = len(signals_df[signals_df['signal'] == 'buy'])
        total_sell = len(signals_df[signals_df['signal'] == 'sell'])
        total_hold = len(signals_df[signals_df['signal'] == 'hold'])
        
        buy_rate = (total_buy / len(signals_df)) * 100
        
        print(f"  Total Signals: {len(signals_df)}")
        print(f"  BUY Rate: {buy_rate:.1f}%")
        print(f"  SELL Rate: {(total_sell / len(signals_df)) * 100:.1f}%")
        print(f"  HOLD Rate: {(total_hold / len(signals_df)) * 100:.1f}%")
        
        if buy_rate >= 30 and buy_rate <= 40:
            print(f"  ✅ BUY rate is within target range (30-40%)")
        elif buy_rate < 30:
            print(f"  ⚠️  BUY rate is below target (30-40%)")
        else:
            print(f"  ⚠️  BUY rate is above target (30-40%)")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_unified_engine_real_data()
