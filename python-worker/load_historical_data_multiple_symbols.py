#!/usr/bin/env python3
"""
Load Historical Data for Multiple Stocks and ETFs
Uses the same data loading approach as TQQQ testing
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

def load_historical_data(symbol: str, start_date: str = '2025-01-01', end_date: str = '2025-12-31') -> pd.DataFrame:
    """
    Load historical data for a symbol using the same approach as TQQQ
    """
    
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
            print(f"❌ No data found for {symbol}")
            return None
        
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
        ])
        df['date'] = pd.to_datetime(df['date'])
        
        print(f"✅ {symbol}: {len(df)} records from {df['date'].min().date()} to {df['date'].max().date()}")
        print(f"   Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        
        return df
        
    except Exception as e:
        print(f"❌ Error loading {symbol}: {e}")
        return None

def create_market_conditions(df: pd.DataFrame, idx: int) -> MarketConditions:
    """
    Create market conditions using the same approach as TQQQ testing
    """
    
    row = df.iloc[idx]
    
    # Skip first few days for volatility calculation
    if idx < 10:
        return None
    
    try:
        # Calculate recent change (2-day lookback like TQQQ)
        recent_close = df.iloc[idx-2]['close']
        recent_change = (row['close'] - recent_close) / recent_close
        
        # Calculate volatility (20-day lookback like TQQQ)
        start_idx = max(0, idx - 19)
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
        print(f"❌ Error creating conditions for {row['date']}: {e}")
        return None

def test_symbol_with_engines(symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
    """
    Test a symbol with both TQQQ engine (for comparison) and appropriate generic engine
    """
    
    print(f"\n🎯 TESTING {symbol}:")
    print("-" * 50)
    
    # Initialize engines
    tqqq_config = SignalConfig(
        rsi_oversold=45,
        rsi_moderately_oversold=35,
        rsi_mildly_oversold=50,
        max_volatility=8.0
    )
    
    tqqq_engine = UnifiedTQQQSwingEngine(tqqq_config)
    generic_engine = create_instrument_engine(symbol)
    
    # Generate signals for all available data
    tqqq_signals = []
    generic_signals = []
    
    for idx, row in df.iterrows():
        conditions = create_market_conditions(df, idx)
        if conditions is None:
            continue
        
        try:
            # Test with TQQQ engine
            tqqq_result = tqqq_engine.generate_signal(conditions)
            tqqq_signals.append({
                'date': row['date'],
                'signal': tqqq_result.signal.value,
                'confidence': tqqq_result.confidence,
                'regime': tqqq_result.metadata.get('regime', 'unknown'),
                'reasoning': tqqq_result.reasoning[0] if tqqq_result.reasoning else "No reasoning"
            })
            
            # Test with generic engine
            generic_result = generic_engine.generate_signal(conditions)
            generic_signals.append({
                'date': row['date'],
                'signal': generic_result.signal.value,
                'confidence': generic_result.confidence,
                'regime': generic_result.metadata.get('regime', 'unknown'),
                'reasoning': generic_result.reasoning[0] if generic_result.reasoning else "No reasoning"
            })
            
        except Exception as e:
            print(f"❌ Error generating signal for {row['date']}: {e}")
            continue
    
    # Convert to DataFrames
    tqqq_df = pd.DataFrame(tqqq_signals)
    generic_df = pd.DataFrame(generic_signals)
    
    # Analyze results
    results = {
        'symbol': symbol,
        'total_signals': len(tqqq_signals),
        'tqqq_engine': analyze_signals(tqqq_df, "TQQQ Engine"),
        'generic_engine': analyze_signals(generic_df, f"Generic {symbol} Engine"),
        'engine_comparison': compare_engines(tqqq_df, generic_df),
        'sample_signals': get_sample_signals(tqqq_df, generic_df, df, 5)
    }
    
    return results

def analyze_signals(signals_df: pd.DataFrame, engine_name: str) -> Dict[str, Any]:
    """Analyze signal distribution and performance"""
    
    if signals_df.empty:
        return {'error': 'No signals generated'}
    
    # Signal distribution
    signal_counts = signals_df['signal'].value_counts()
    total_signals = len(signals_df)
    
    # Confidence statistics
    confidence_stats = signals_df['confidence'].describe()
    
    # Regime distribution
    regime_counts = signals_df['regime'].value_counts()
    
    return {
        'total_signals': total_signals,
        'signal_distribution': signal_counts.to_dict(),
        'signal_percentages': (signal_counts / total_signals * 100).round(1).to_dict(),
        'confidence_stats': {
            'mean': confidence_stats['mean'],
            'std': confidence_stats['std'],
            'min': confidence_stats['min'],
            'max': confidence_stats['max']
        },
        'regime_distribution': regime_counts.to_dict(),
        'engine_name': engine_name
    }

def compare_engines(tqqq_df: pd.DataFrame, generic_df: pd.DataFrame) -> Dict[str, Any]:
    """Compare TQQQ engine vs generic engine results"""
    
    if tqqq_df.empty or generic_df.empty:
        return {'error': 'Insufficient data for comparison'}
    
    # Align dataframes by date
    comparison_df = pd.merge(
        tqqq_df[['date', 'signal', 'confidence']], 
        generic_df[['date', 'signal', 'confidence']], 
        on='date', 
        suffixes=('_tqqq', '_generic')
    )
    
    # Calculate agreement
    agreement = (comparison_df['signal_tqqq'] == comparison_df['signal_generic']).mean()
    
    # Signal differences
    signal_diff = comparison_df[comparison_df['signal_tqqq'] != comparison_df['signal_generic']]
    
    return {
        'total_comparisons': len(comparison_df),
        'agreement_rate': f"{agreement:.1%}",
        'disagreements': len(signal_diff),
        'agreement_by_signal': {
            signal: (comparison_df[comparison_df['signal_tqqq'] == signal]['signal_tqqq'] == 
                    comparison_df[comparison_df['signal_tqqq'] == signal]['signal_generic']).mean()
            for signal in comparison_df['signal_tqqq'].unique()
        }
    }

def get_sample_signals(tqqq_df: pd.DataFrame, generic_df: pd.DataFrame, price_df: pd.DataFrame, n_samples: int) -> List[Dict[str, Any]]:
    """Get sample signals with price data"""
    
    if tqqq_df.empty or generic_df.empty:
        return []
    
    # Get recent samples
    recent_dates = tqqq_df.tail(n_samples)['date']
    
    samples = []
    for date in recent_dates:
        price_row = price_df[price_df['date'] == date].iloc[0]
        tqqq_row = tqqq_df[tqqq_df['date'] == date].iloc[0]
        generic_row = generic_df[generic_df['date'] == date].iloc[0]
        
        samples.append({
            'date': date.date(),
            'price': price_row['close'],
            'rsi': price_row['rsi'],
            'tqqq_signal': tqqq_row['signal'],
            'tqqq_confidence': tqqq_row['confidence'],
            'generic_signal': generic_row['signal'],
            'generic_confidence': generic_row['confidence'],
            'agreement': tqqq_row['signal'] == generic_row['signal']
        })
    
    return samples

def main():
    """Main function to test all specified symbols"""
    
    print("🚀 LOADING HISTORICAL DATA FOR STOCKS AND ETFS")
    print("=" * 60)
    
    # Symbols to test
    stocks = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV']
    etfs = ['QQQ', 'SMH']
    all_symbols = stocks + etfs
    
    print(f"📊 Testing {len(stocks)} stocks and {len(etfs)} ETFs")
    print(f"🔤 Symbols: {', '.join(all_symbols)}")
    print()
    
    # Load data for all symbols
    all_data = {}
    
    for symbol in all_symbols:
        print(f"📈 Loading {symbol}...")
        df = load_historical_data(symbol)
        if df is not None:
            all_data[symbol] = df
        print()
    
    if not all_data:
        print("❌ No data loaded for any symbols")
        return
    
    print(f"✅ Successfully loaded data for {len(all_data)} symbols")
    print()
    
    # Test each symbol
    all_results = {}
    
    for symbol, df in all_data.items():
        try:
            results = test_symbol_with_engines(symbol, df)
            all_results[symbol] = results
            
            # Print summary
            print(f"📊 {symbol} Summary:")
            print(f"   Total Signals: {results['total_signals']}")
            
            if 'error' not in results['tqqq_engine']:
                tqqq = results['tqqq_engine']
                print(f"   TQQQ Engine - BUY: {tqqq['signal_percentages'].get('BUY', 0):.1f}%, "
                      f"SELL: {tqqq['signal_percentages'].get('SELL', 0):.1f}%, "
                      f"HOLD: {tqqq['signal_percentages'].get('HOLD', 0):.1f}%")
            
            if 'error' not in results['generic_engine']:
                generic = results['generic_engine']
                print(f"   Generic Engine - BUY: {generic['signal_percentages'].get('BUY', 0):.1f}%, "
                      f"SELL: {generic['signal_percentages'].get('SELL', 0):.1f}%, "
                      f"HOLD: {generic['signal_percentages'].get('HOLD', 0):.1f}%")
            
            if 'error' not in results['engine_comparison']:
                comp = results['engine_comparison']
                print(f"   Engine Agreement: {comp['agreement_rate']}")
            
            print()
            
        except Exception as e:
            print(f"❌ Error testing {symbol}: {e}")
            print()
            continue
    
    # Print overall summary
    print("🎯 OVERALL SUMMARY")
    print("=" * 60)
    
    for symbol, results in all_results.items():
        if 'error' not in results['engine_comparison']:
            comp = results['engine_comparison']
            print(f"{symbol:8} | Agreement: {comp['agreement_rate']:>6} | "
                  f"Signals: {results['total_signals']:>4} | "
                  f"Disagreements: {comp['disagreements']:>3}")
    
    print()
    print("🎉 Historical data loading and testing complete!")

if __name__ == "__main__":
    main()
