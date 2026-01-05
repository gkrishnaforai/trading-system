#!/usr/bin/env python3
"""
Swing Trading Engine Test for Multiple Symbols
Tests both TQQQ and generic engines with loaded historical data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Import engines
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.generic_etf_engine import create_instrument_engine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def load_historical_data(symbol: str, start_date: str = '2024-01-01', end_date: str = '2025-12-31') -> pd.DataFrame:
    """Load historical data for a symbol"""
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = %s 
            AND i.date >= %s 
            AND i.date <= %s
            ORDER BY i.date
        """, (symbol, start_date, end_date))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
        ])
        df['date'] = pd.to_datetime(df['date'])
        
        return df
        
    except Exception as e:
        print(f"❌ Error loading {symbol}: {e}")
        return None

def create_market_conditions(df: pd.DataFrame, idx: int) -> MarketConditions:
    """Create market conditions using TQQQ approach with limited data handling"""
    
    row = df.iloc[idx]
    
    # Skip first few days for volatility calculation
    if idx < 2:
        print(f"   ⚠️  Skipping {row['date'].date()} - insufficient data for volatility calculation")
        return None
    
    try:
        # Calculate recent change (2-day lookback like TQQQ)
        if idx >= 2:
            recent_close = df.iloc[idx-2]['close']
            recent_change = (row['close'] - recent_close) / recent_close
        else:
            recent_change = 0.0  # Default if no historical data
        
        # Calculate volatility (use available data, not fixed 20 days)
        start_idx = max(0, idx - min(19, len(df) - 1))
        volatility_data = df.iloc[start_idx:idx+1]['close'].pct_change().dropna()
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
        
        return conditions
        
    except Exception as e:
        print(f"   ❌ Error creating conditions for {row['date']}: {e}")
        return None

def test_symbol_engines(symbol: str, df: pd.DataFrame, sample_size: int = 10) -> Dict[str, Any]:
    """Test a symbol with both engines and show sample results"""
    
    print(f"\n🎯 TESTING {symbol} SWING ENGINES")
    print("=" * 50)
    
    # Initialize engines
    tqqq_config = SignalConfig(
        rsi_oversold=45,
        rsi_moderately_oversold=35,
        rsi_mildly_oversold=50,
        max_volatility=8.0
    )
    
    tqqq_engine = UnifiedTQQQSwingEngine(tqqq_config)
    generic_engine = create_instrument_engine(symbol)
    
    print(f"📊 Data: {len(df)} records from {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"💰 Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
    print(f"📈 Volatility: {df['close'].pct_change().std() * 100:.2f}%")
    print()
    
    # Generate signals for sample dates
    sample_indices = np.linspace(10, len(df)-1, sample_size, dtype=int)
    
    results = []
    
    for idx in sample_indices:
        conditions = create_market_conditions(df, idx)
        if conditions is None:
            continue
        
        row = df.iloc[idx]
        
        try:
            # Test with TQQQ engine
            tqqq_result = tqqq_engine.generate_signal(conditions)
            
            # Test with generic engine
            generic_result = generic_engine.generate_signal(conditions)
            
            result_data = {
                'date': row['date'].date(),
                'price': row['close'],
                'rsi': row['rsi'],
                'sma20': row['ema_20'],
                'sma50': row['sma_50'],
                'recent_change': conditions.recent_change * 100,
                'volatility': conditions.volatility,
                'tqqq_signal': tqqq_result.signal.value,
                'tqqq_confidence': tqqq_result.confidence,
                'tqqq_regime': tqqq_result.metadata.get('regime', 'unknown'),
                'tqqq_reasoning': tqqq_result.reasoning[0] if tqqq_result.reasoning else "No reasoning",
                'generic_signal': generic_result.signal.value,
                'generic_confidence': generic_result.confidence,
                'generic_regime': generic_result.metadata.get('regime', 'unknown'),
                'generic_reasoning': generic_result.reasoning[0] if generic_result.reasoning else "No reasoning",
                'agreement': tqqq_result.signal.value == generic_result.signal.value
            }
            
            results.append(result_data)
            
        except Exception as e:
            print(f"❌ Error for {row['date']}: {e}")
            continue
    
    # Print sample results
    print(f"📋 SAMPLE SIGNALS ({len(results)} samples):")
    print("-" * 100)
    print(f"{'Date':<12} {'Price':<8} {'RSI':<6} {'TQQQ':<12} {'Generic':<12} {'Agree':<6} {'TQQQ Reasoning':<25}")
    print("-" * 100)
    
    for result in results:
        tqqq_signal = f"{result['tqqq_signal'][:4]}({result['tqqq_confidence']:.2f})"
        generic_signal = f"{result['generic_signal'][:4]}({result['generic_confidence']:.2f})"
        agreement = "✅" if result['agreement'] else "❌"
        
        # Truncate reasoning for display
        tqqq_reasoning = result['tqqq_reasoning'][:24] + "..." if len(result['tqqq_reasoning']) > 25 else result['tqqq_reasoning']
        
        print(f"{result['date']:<12} ${result['price']:<7.2f} {result['rsi']:<6.1f} "
              f"{tqqq_signal:<12} {generic_signal:<12} {agreement:<6} {tqqq_reasoning:<25}")
    
    # Analyze overall results
    if results:
        results_df = pd.DataFrame(results)
        
        # Signal distribution
        tqqq_dist = results_df['tqqq_signal'].value_counts()
        generic_dist = results_df['generic_signal'].value_counts()
        
        # Agreement rate
        agreement_rate = results_df['agreement'].mean()
        
        print(f"\n📊 ANALYSIS SUMMARY:")
        print(f"   Total samples: {len(results)}")
        print(f"   Agreement rate: {agreement_rate:.1%}")
        print(f"   TQQQ signals: BUY {tqqq_dist.get('BUY', 0)}, SELL {tqqq_dist.get('SELL', 0)}, HOLD {tqqq_dist.get('HOLD', 0)}")
        print(f"   Generic signals: BUY {generic_dist.get('BUY', 0)}, SELL {generic_dist.get('SELL', 0)}, HOLD {generic_dist.get('HOLD', 0)}")
        
        # Engine info
        generic_metadata = generic_engine.get_engine_metadata()
        print(f"   Generic engine: {generic_metadata['display_name']}")
        print(f"   Engine type: {generic_metadata.get('etf_type', 'stock').upper()}")
        
    return {
        'symbol': symbol,
        'samples': len(results),
        'agreement_rate': results_df['agreement'].mean() if results else 0,
        'results': results
    }

def main():
    """Main function to test swing engines on multiple symbols"""
    
    print("🚀 SWING TRADING ENGINE TEST")
    print("=" * 60)
    
    # Symbols to test
    stocks = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV']
    etfs = ['QQQ', 'SMH']
    all_symbols = stocks + etfs
    
    print(f"🔤 Testing {len(stocks)} stocks and {len(etfs)} ETFs")
    print(f"📊 Symbols: {', '.join(all_symbols)}")
    print()
    
    # Test each symbol
    all_results = {}
    
    for symbol in all_symbols:
        print(f"📈 Loading {symbol} data...")
        
        # Load data
        df = load_historical_data(symbol)
        
        if df is None:
            print(f"❌ No data available for {symbol}")
            print()
            continue
        
        # Test engines
        try:
            results = test_symbol_engines(symbol, df, sample_size=15)
            all_results[symbol] = results
        except Exception as e:
            print(f"❌ Error testing {symbol}: {e}")
        
        print()
    
    # Overall summary
    print("🎯 OVERALL SUMMARY")
    print("=" * 60)
    
    if all_results:
        print(f"{'Symbol':<8} {'Samples':<8} {'Agreement':<10} {'TQQQ BUY':<9} {'Generic BUY':<11}")
        print("-" * 60)
        
        for symbol, results in all_results.items():
            samples = results['samples']
            agreement = f"{results['agreement_rate']:.1%}"
            
            # Count BUY signals
            tqqq_buy = sum(1 for r in results['results'] if r['tqqq_signal'] == 'BUY')
            generic_buy = sum(1 for r in results['results'] if r['generic_signal'] == 'BUY')
            
            print(f"{symbol:<8} {samples:<8} {agreement:<10} {tqqq_buy:<9} {generic_buy:<11}")
        
        print()
        print(f"✅ Successfully tested {len(all_results)}/{len(all_symbols)} symbols")
        
        # Average agreement
        avg_agreement = np.mean([r['agreement_rate'] for r in all_results.values()])
        print(f"📊 Average engine agreement: {avg_agreement:.1%}")
    
    else:
        print("❌ No symbols tested successfully")
    
    print()
    print("🎉 Swing trading engine test complete!")
    print()
    print("💡 Key insights:")
    print("   - TQQQ engine uses aggressive volatility detection (4% threshold)")
    print("   - Generic engines use symbol-specific configurations")
    print("   - Agreement varies by symbol type and volatility characteristics")
    print("   - Both engines always generate BUY/SELL/HOLD signals")

if __name__ == "__main__":
    main()
