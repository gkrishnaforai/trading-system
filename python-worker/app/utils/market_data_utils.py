#!/usr/bin/env python3
"""
Market Data Utilities
Calculate real volatility and recent changes from historical data
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional
import psycopg2
import os
from sqlalchemy import create_engine

def calculate_real_market_metrics(symbol: str, target_date: str, db_url: str) -> Tuple[float, float]:
    """
    Calculate real volatility and recent change for a symbol
    
    Returns:
        Tuple[float, float]: (volatility_percent, recent_change_percent)
    """
    
    try:
        # Use SQLAlchemy engine to avoid pandas warnings
        engine = create_engine(db_url)
        
        # Get 30 days of historical data for calculations
        query = """
            SELECT date, close, high, low, volume
            FROM raw_market_data_daily 
            WHERE symbol = %s 
            AND date <= %s::date
            ORDER BY date DESC
            LIMIT 30
        """
        
        df = pd.read_sql(query, engine, params=(symbol, target_date))
        
        if len(df) < 5:
            # Not enough data, return defaults
            return 2.0, 0.0
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')  # Sort chronologically
        
        # Calculate daily returns
        df['daily_return'] = df['close'].pct_change()
        
        # Calculate volatility (standard deviation of daily returns * 100)
        volatility = df['daily_return'].std() * 100
        
        # Calculate recent change (3-day change)
        if len(df) >= 4:
            current_price = df['close'].iloc[-1]
            price_3_days_ago = df['close'].iloc[-4]
            recent_change = (current_price - price_3_days_ago) / price_3_days_ago * 100
        else:
            # Use 1-day change if not enough data
            if len(df) >= 2:
                current_price = df['close'].iloc[-1]
                previous_price = df['close'].iloc[-2]
                recent_change = (current_price - previous_price) / previous_price * 100
            else:
                recent_change = 0.0
        
        return float(volatility), float(recent_change)
        
    except Exception as e:
        print(f"Error calculating metrics for {symbol}: {e}")
        return 2.0, 0.0

def get_vix_level(target_date: str, db_url: str) -> float:
    """
    Get VIX level for a specific date
    
    Returns:
        float: VIX level or 20.0 as default
    """
    
    try:
        # Use SQLAlchemy engine to avoid pandas warnings
        engine = create_engine(db_url)
        
        # Try ^VIX first (more recent data), then VIX
        for vix_symbol in ['^VIX', 'VIX']:
            query = """
                SELECT close
                FROM raw_market_data_daily 
                WHERE symbol = %s 
                AND date <= %s::date
                ORDER BY date DESC
                LIMIT 1
            """
            
            df = pd.read_sql(query, engine, params=(vix_symbol, target_date))
            
            if not df.empty:
                vix_level = float(df['close'].iloc[0])
                return float(vix_level)
        
        return 20.0  # Default VIX level
        
    except Exception as e:
        print(f"Error getting VIX level: {e}")
        return 20.0

def get_symbol_indicators_data(symbol: str, target_date: str, db_url: str) -> dict:
    """
    Get symbol data using same indicators methodology as TQQQ backtest
    This provides consistent data source for all symbols
    
    Args:
        symbol: Stock/ETF symbol
        target_date: Target date for analysis
        db_url: Database URL
    
    Returns:
        dict: Symbol data with indicators or None if not found
    """
    try:
        from sqlalchemy import create_engine, text
        
        engine = create_engine(db_url)
        
        # Build the same query as TQQQ API but for any symbol
        query = """
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = :symbol AND i.date = :target_date
            ORDER BY i.date
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {"symbol": symbol.upper(), "target_date": target_date})
            rows = result.fetchall()
            
            if not rows:
                # Try to get most recent data if specific date not found
                query_latest = """
                    SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                    FROM indicators_daily i
                    JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                    WHERE i.symbol = :symbol
                    ORDER BY i.date DESC
                    LIMIT 1
                """
                result = conn.execute(text(query_latest), {"symbol": symbol.upper()})
                rows = result.fetchall()
            
            if not rows:
                return None
            
            row = rows[0]
            
            return {
                'date': row[0],
                'close': row[1],
                'rsi_14': row[2],
                'sma_50': row[3],
                'ema_20': row[4],
                'macd': row[5],
                'macd_signal': row[6],
                'volume': row[7],
                'low': row[8],
                'high': row[9]
            }
            
    except Exception as e:
        print(f"Error getting symbol indicators data for {symbol}: {e}")
        return None

def calculate_market_regime_context(symbol: str, target_date: str, db_url: str, asset_type: str = "stock") -> dict:
    """
    Calculate comprehensive market context for regime detection
    Enhanced version with asset-type-specific calculations
    
    Args:
        symbol: Stock/ETF symbol
        target_date: Target date for analysis
        db_url: Database URL
        asset_type: "3x_etf", "regular_etf", or "stock"
    
    Returns:
        dict: Market context with volatility, VIX, recent changes, etc.
    """
    
    # Calculate symbol-specific metrics with asset-type adjustments
    volatility, recent_change = calculate_real_market_metrics(symbol, target_date, db_url)
    
    # Get VIX level (fear-and-greed indicator - same as TQQQ backtest)
    vix_level = get_vix_level(target_date, db_url)
    
    # Asset-type-specific volatility thresholds
    if asset_type == "3x_etf":
        # 3x ETFs are more volatile - use higher thresholds
        vol_threshold_high = 8.0
        vol_threshold_moderate = 4.0
    elif asset_type == "regular_etf":
        # Regular ETFs have moderate volatility
        vol_threshold_high = 5.0
        vol_threshold_moderate = 2.5
    else:  # stock
        # Stocks have standard volatility thresholds
        vol_threshold_high = 6.0
        vol_threshold_moderate = 3.0
    
    # Determine market stress level (same as TQQQ backtest)
    vix_stress = "LOW" if vix_level < 20 else "MODERATE" if vix_level < 30 else "HIGH"
    
    # Determine volatility level with asset-type thresholds
    if volatility > vol_threshold_high:
        vol_level = "HIGH"
    elif volatility > vol_threshold_moderate:
        vol_level = "MODERATE"
    else:
        vol_level = "LOW"
    
    # Market stress calculation (same as TQQQ backtest)
    market_stress = bool(vix_stress == "HIGH" or volatility > 4.0)
    
    return {
        'volatility': float(volatility),
        'recent_change': float(recent_change),
        'vix_level': float(vix_level),
        'vix_stress': vix_stress,
        'volatility_level': vol_level,
        'market_stress': market_stress,
        'asset_type': asset_type,
        'volatility_thresholds': {
            'high': vol_threshold_high,
            'moderate': vol_threshold_moderate
        }
    }

def test_calculations():
    """Test the calculation functions"""
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://trading:trading-dev@localhost:5432/trading_system?sslmode=disable')
    
    # Test with TQQQ for the dates we analyzed
    test_dates = ['2025-05-20', '2025-05-21']
    
    print("🔍 Testing Real Market Calculations")
    print("=" * 50)
    
    for date in test_dates:
        print(f"\n📅 {date}:")
        
        # Calculate metrics
        context = calculate_market_regime_context('TQQQ', date, db_url)
        
        print(f"   Volatility: {context['volatility']:.2f}% ({context['volatility_level']})")
        print(f"   Recent Change: {context['recent_change']:.2f}%")
        print(f"   VIX Level: {context['vix_level']:.2f} ({context['vix_stress']})")
        print(f"   Market Stress: {context['market_stress']}")

if __name__ == "__main__":
    test_calculations()
