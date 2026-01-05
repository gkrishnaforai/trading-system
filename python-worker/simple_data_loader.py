#!/usr/bin/env python3
"""
Simple Historical Data Loader for Multiple Symbols
Loads data using the same approach as TQQQ testing
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any

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
        
        return df
        
    except Exception as e:
        print(f"❌ Error loading {symbol}: {e}")
        return None

def analyze_data_quality(df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
    """Analyze data quality and basic statistics"""
    
    if df is None or df.empty:
        return {'error': 'No data available'}
    
    # Basic stats
    price_stats = df['close'].describe()
    rsi_stats = df['rsi'].describe()
    volume_stats = df['volume'].describe()
    
    # Data completeness
    null_counts = df.isnull().sum()
    
    # Price changes
    df['daily_change'] = df['close'].pct_change() * 100
    volatility = df['daily_change'].std()
    
    # RSI distribution
    rsi_oversold = (df['rsi'] < 30).sum()
    rsi_overbought = (df['rsi'] > 70).sum()
    rsi_neutral = len(df) - rsi_oversold - rsi_overbought
    
    return {
        'symbol': symbol,
        'data_points': len(df),
        'date_range': {
            'start': df['date'].min().date(),
            'end': df['date'].max().date(),
            'trading_days': len(df)
        },
        'price_analysis': {
            'min': price_stats['min'],
            'max': price_stats['max'],
            'mean': price_stats['mean'],
            'std': price_stats['std'],
            'range': price_stats['max'] - price_stats['min'],
            'volatility': volatility
        },
        'rsi_analysis': {
            'min': rsi_stats['min'],
            'max': rsi_stats['max'],
            'mean': rsi_stats['mean'],
            'oversold_days': rsi_oversold,
            'overbought_days': rsi_overbought,
            'neutral_days': rsi_neutral,
            'oversold_pct': (rsi_oversold / len(df) * 100),
            'overbought_pct': (rsi_overbought / len(df) * 100)
        },
        'volume_analysis': {
            'mean': volume_stats['mean'],
            'median': df['volume'].median(),
            'min': volume_stats['min'],
            'max': volume_stats['max']
        },
        'data_quality': {
            'null_values': null_counts.to_dict(),
            'completeness': (1 - null_counts.sum() / (len(df) * len(df.columns))) * 100
        }
    }

def main():
    """Load and analyze data for all specified symbols"""
    
    print("📊 LOADING HISTORICAL DATA FOR STOCKS AND ETFS")
    print("=" * 60)
    
    # Symbols to test
    stocks = ['SOFI', 'NVDA', 'AVGO', 'MU', 'GOOGL', 'APLD', 'IREN', 'ZETA', 'NBIS', 'CRWV']
    etfs = ['QQQ', 'SMH']
    all_symbols = stocks + etfs
    
    print(f"🔤 Loading data for {len(all_symbols)} symbols:")
    print(f"   Stocks: {', '.join(stocks)}")
    print(f"   ETFs: {', '.join(etfs)}")
    print()
    
    # Load and analyze data for all symbols
    all_data = {}
    all_analysis = {}
    
    for symbol in all_symbols:
        print(f"📈 Loading {symbol}...")
        
        # Load data
        df = load_historical_data(symbol)
        
        if df is not None:
            all_data[symbol] = df
            analysis = analyze_data_quality(df, symbol)
            all_analysis[symbol] = analysis
            
            # Print basic info
            print(f"   ✅ {len(df)} records from {analysis['date_range']['start']} to {analysis['date_range']['end']}")
            print(f"   💰 Price: ${analysis['price_analysis']['min']:.2f} - ${analysis['price_analysis']['max']:.2f}")
            print(f"   📊 Volatility: {analysis['price_analysis']['volatility']:.2f}%")
            print(f"   🎯 RSI: {analysis['rsi_analysis']['oversold_pct']:.1f}% oversold, {analysis['rsi_analysis']['overbought_pct']:.1f}% overbought")
            print(f"   ✅ Data Quality: {analysis['data_quality']['completeness']:.1f}% complete")
        else:
            print(f"   ❌ No data available")
        
        print()
    
    # Summary table
    print("📋 SUMMARY TABLE")
    print("=" * 100)
    print(f"{'Symbol':<8} {'Records':<8} {'Date Range':<22} {'Price Range':<15} {'Volatility':<10} {'RSI Range':<12} {'Quality':<8}")
    print("-" * 100)
    
    for symbol in all_symbols:
        if symbol in all_analysis:
            analysis = all_analysis[symbol]
            date_range = f"{analysis['date_range']['start']} to {analysis['date_range']['end']}"
            price_range = f"${analysis['price_analysis']['min']:.2f}-${analysis['price_analysis']['max']:.2f}"
            rsi_range = f"{analysis['rsi_analysis']['min']:.1f}-{analysis['rsi_analysis']['max']:.1f}"
            
            print(f"{symbol:<8} {analysis['data_points']:<8} {date_range:<22} {price_range:<15} "
                  f"{analysis['price_analysis']['volatility']:.2f}%{'':<6} {rsi_range:<12} "
                  f"{analysis['data_quality']['completeness']:.1f}%")
        else:
            print(f"{symbol:<8} {'NO DATA':<8} {'N/A':<22} {'N/A':<15} {'N/A':<10} {'N/A':<12} {'N/A':<8}")
    
    print()
    
    # Success statistics
    successful_symbols = [s for s in all_symbols if s in all_analysis]
    print(f"✅ Successfully loaded {len(successful_symbols)}/{len(all_symbols)} symbols")
    
    if successful_symbols:
        print(f"📅 Date range coverage: {min(all_analysis[s]['date_range']['start'] for s in successful_symbols)} "
              f"to {max(all_analysis[s]['date_range']['end'] for s in successful_symbols)}")
        print(f"📊 Total data points: {sum(all_analysis[s]['data_points'] for s in successful_symbols)}")
    
    print()
    print("🎉 Data loading complete!")
    print()
    print("💡 Next steps:")
    print("   1. Use this data with swing trading engines")
    print("   2. Test signal generation for each symbol")
    print("   3. Compare performance across different instruments")
    
    return all_data, all_analysis

if __name__ == "__main__":
    data, analysis = main()
