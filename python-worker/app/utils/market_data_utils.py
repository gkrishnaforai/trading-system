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
    Get VIX level for a specific date from macro_market_data table
    
    Returns:
        float: VIX level or 20.0 as default
    """
    
    try:
        # Use SQLAlchemy engine to avoid pandas warnings
        engine = create_engine(db_url)
        
        # Query macro_market_data table where VIX data is stored
        query = """
            SELECT vix_close, data_date
            FROM macro_market_data 
            WHERE data_date <= %s::date
            ORDER BY data_date DESC
            LIMIT 1
        """
        
        df = pd.read_sql(query, engine, params=(target_date,))
        
        if not df.empty:
            vix_level = float(df['vix_close'].iloc[0])
            actual_date = df['data_date'].iloc[0]
            print(f"🔍 VIX Debug: Target={target_date}, Found={actual_date}, VIX={vix_level}")
            return float(vix_level)
        else:
            print(f"⚠️ VIX Debug: No data found for target={target_date}")
        
        return 20.0  # Default VIX level
        
    except Exception as e:
        print(f"❌ Error getting VIX level: {e}")
        return 20.0

def calculate_ema_slope(symbol: str, target_date: str, db_url: str) -> float:
    """
    Calculate EMA20 slope (trend direction)
    
    Returns:
        float: Slope value (positive = upward, negative = downward)
    """
    try:
        engine = create_engine(db_url)
        
        # Get unique EMA20 for last 5 days to calculate slope (handle duplicates)
        slope_query = """
            SELECT DISTINCT date, 
                   FIRST_VALUE(ema_20) OVER (PARTITION BY date ORDER BY created_at DESC) as ema_20
            FROM indicators_daily 
            WHERE symbol = %s 
            AND date <= %s::date
            ORDER BY date DESC
            LIMIT 5
        """
        
        df = pd.read_sql(slope_query, engine, params=(symbol.upper(), target_date))
        
        print(f"🔍 EMA Slope Debug for {symbol}: Found {len(df)} unique EMA data points")
        if len(df) > 0:
            print(f"📊 EMA Data:")
            for i, row in df.iterrows():
                print(f"   Day {i}: {row['date']} -> EMA20: {row['ema_20']}")
        
        if len(df) >= 2:
            # Calculate simple slope using most recent 2 unique dates
            ema_recent = float(df.iloc[0]['ema_20'])
            ema_previous = float(df.iloc[1]['ema_20'])
            slope = ema_recent - ema_previous
            
            print(f"📈 EMA20 Slope for {symbol}: {slope:+.4f} (Recent: {ema_recent:.2f}, Previous: {ema_previous:.2f})")
            
            # Additional debug for flat EMA
            if abs(slope) < 0.0001:
                print(f"⚠️ EMA values nearly identical: {ema_recent:.6f} vs {ema_previous:.6f}")
            
            return slope
        else:
            print(f"❌ Insufficient EMA data for {symbol}: need at least 2 points, got {len(df)}")
            return 0.0
        
    except Exception as e:
        print(f"❌ Error calculating EMA slope for {symbol}: {e}")
        return 0.0

def calculate_relative_strength(symbol: str, target_date: str, db_url: str) -> float:
    """
    Calculate stock's 5-day return relative to SPY market performance
    
    Returns:
        float: Relative strength (stock_return - spy_return)
    """
    try:
        engine = create_engine(db_url)
        
        # Get stock 5-day return
        stock_query = """
            SELECT (close - LAG(close, 4) OVER (ORDER BY date)) / LAG(close, 4) OVER (ORDER BY date) as stock_return
            FROM raw_market_data_daily 
            WHERE symbol = %s 
            AND date <= %s::date
            ORDER BY date DESC
            LIMIT 1
        """
        
        stock_df = pd.read_sql(stock_query, engine, params=(symbol.upper(), target_date))
        
        # Get SPY 5-day return
        spy_query = """
            SELECT (close - LAG(close, 4) OVER (ORDER BY date)) / LAG(close, 4) OVER (ORDER BY date) as spy_return
            FROM raw_market_data_daily 
            WHERE symbol = 'SPY' 
            AND date <= %s::date
            ORDER BY date DESC
            LIMIT 1
        """
        
        spy_df = pd.read_sql(spy_query, engine, params=(target_date,))
        
        if not stock_df.empty and not spy_df.empty:
            stock_return = float(stock_df['stock_return'].iloc[0] or 0)
            spy_return = float(spy_df['spy_return'].iloc[0] or 0)
            relative_strength = stock_return - spy_return
            
            print(f"🏎️ Relative Strength for {symbol}: {relative_strength:+.3f} (Stock: {stock_return:+.3f}, SPY: {spy_return:+.3f})")
            return relative_strength
        
        return 0.0
        
    except Exception as e:
        print(f"Error calculating relative strength: {e}")
        return 0.0

def check_price_stability(symbol: str, target_date: str, db_url: str) -> dict:
    """
    Check for price stabilization patterns (no new lows, shrinking ranges)
    
    Returns:
        dict: Stability metrics
    """
    try:
        engine = create_engine(db_url)
        
        # Get last 5 days for stability analysis
        stability_query = """
            SELECT date, close, high, low, volume
            FROM raw_market_data_daily 
            WHERE symbol = %s 
            AND date <= %s::date
            ORDER BY date DESC
            LIMIT 5
        """
        
        df = pd.read_sql(stability_query, engine, params=(symbol.upper(), target_date))
        
        if len(df) >= 3:
            # Check for new lower lows
            recent_low = float(df.iloc[0]['low'])
            previous_low_2d = float(df.iloc[2]['low'])
            no_new_lows = recent_low >= previous_low_2d
            
            # Check daily ranges (shrinking or stable)
            current_range = float(df.iloc[0]['high']) - float(df.iloc[0]['low'])
            avg_range = df['high'].astype(float) - df['low'].astype(float)
            avg_range = avg_range.mean()
            range_stable = current_range <= (avg_range * 1.1)  # Within 10% of average
            
            # Check if close is in upper half of candle
            current_close = float(df.iloc[0]['close'])
            current_high = float(df.iloc[0]['high'])
            current_low = float(df.iloc[0]['low'])
            close_upper_half = current_close >= (current_high + current_low) / 2
            
            stability_score = sum([no_new_lows, range_stable, close_upper_half]) / 3
            
            print(f"📊 Price Stability for {symbol}:")
            print(f"   No new lows (3d): {'✅' if no_new_lows else '❌'}")
            print(f"   Range stable: {'✅' if range_stable else '❌'}")
            print(f"   Close upper half: {'✅' if close_upper_half else '❌'}")
            print(f"   Stability Score: {stability_score:.2f}")
            
            return {
                'no_new_lows': no_new_lows,
                'range_stable': range_stable,
                'close_upper_half': close_upper_half,
                'stability_score': stability_score
            }
        
        return {'stability_score': 0.0}
        
    except Exception as e:
        print(f"Error checking price stability: {e}")
        return {'stability_score': 0.0}

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
            SELECT i.date, r.close, r.open, r.high, r.low, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume
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
                    SELECT i.date, r.close, r.open, r.high, r.low, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume
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
            
            # Calculate 20-day average volume
            avg_volume_20d = 0.0
            try:
                volume_query = """
                    SELECT AVG(r.volume) as avg_volume
                    FROM raw_market_data_daily r
                    WHERE r.symbol = %s 
                    AND r.date <= %s
                    AND r.date >= %s::date - INTERVAL '20 days'
                """
                volume_df = pd.read_sql(volume_query, engine, params=(symbol.upper(), row[0], row[0]))
                if not volume_df.empty and volume_df['avg_volume'].iloc[0] is not None:
                    avg_volume_20d = float(volume_df['avg_volume'].iloc[0])
            except Exception as e:
                print(f"Error calculating 20-day average volume for {symbol}: {e}")
                avg_volume_20d = 0.0
            
            # Enhanced volume and price analysis
            current_volume = float(row[10]) if row[10] is not None else 0.0
            open_price = float(row[2]) if row[2] is not None else 0.0
            close_price = float(row[1]) if row[1] is not None else 0.0
            high_price = float(row[3]) if row[3] is not None else 0.0
            low_price = float(row[4]) if row[4] is not None else 0.0
            ema_20 = float(row[7]) if row[7] is not None else 0.0
            
            # Critical Analysis #1: Trend Confirmation Trigger
            trend_confirmation = False
            trend_confirmation_reason = ""
            
            # Rule 1a: Price > EMA20
            if close_price > ema_20 and ema_20 > 0:
                trend_confirmation = True
                trend_confirmation_reason = f"Price (${close_price:.2f}) > EMA20 (${ema_20:.2f})"
            else:
                # Rule 1b: EMA20 turning upward (slope > 0)
                ema_slope = calculate_ema_slope(symbol, target_date, db_url)
                if ema_slope > 0.01:  # Small positive threshold
                    trend_confirmation = True
                    trend_confirmation_reason = f"EMA20 turning upward (slope: {ema_slope:+.4f})"
                else:
                    trend_confirmation_reason = f"Price (${close_price:.2f}) <= EMA20 (${ema_20:.2f}) and EMA slope: {ema_slope:+.4f}"
            
            # Critical Analysis #2: Volume-Price Relationship
            volume_price_confirmation = False
            volume_price_reason = ""
            
            # Rule 2: Close > Open on high volume
            price_action_bullish = close_price > open_price
            high_volume = current_volume > (avg_volume_20d * 1.2)  # 1.2x average volume
            
            if price_action_bullish and high_volume:
                volume_price_confirmation = True
                volume_price_reason = f"Bullish candle (${open_price:.2f} → ${close_price:.2f}) on high volume ({current_volume/avg_volume_20d:.1f}x avg)"
            elif price_action_bullish and not high_volume:
                volume_price_reason = f"Bullish candle but low volume ({current_volume/avg_volume_20d:.1f}x avg) - Potential fake pump"
            elif not price_action_bullish and high_volume:
                volume_price_reason = f"Bearish candle on high volume - Strong selling pressure"
            else:
                volume_price_reason = f"Bearish candle on low volume - Weak selling pressure"
            
            # Get recovery analysis data
            relative_strength = calculate_relative_strength(symbol, target_date, db_url)
            price_stability = check_price_stability(symbol, target_date, db_url)
            
            print(f"🎯 Critical Analysis for {symbol}:")
            print(f"   Trend Confirmation: {'✅ YES' if trend_confirmation else '❌ NO'} - {trend_confirmation_reason}")
            print(f"   Volume-Price: {'✅ YES' if volume_price_confirmation else '❌ NO'} - {volume_price_reason}")
            print(f"   Relative Strength: {relative_strength:+.3f}")
            print(f"   Price Stability: {price_stability.get('stability_score', 0):.2f}")
            
            print(f"📊 {symbol} Volume Analysis:")
            print(f"   Current Volume: {current_volume:,.0f}")
            print(f"   20d Avg Volume: {avg_volume_20d:,.0f}")
            print(f"   Volume Ratio: {current_volume/avg_volume_20d:.2f}x" if avg_volume_20d > 0 else "   Volume Ratio: N/A")
            print(f"   Price Range: ${low_price:.2f} - ${high_price:.2f}")
            
            # MACD calculation verification - FIXED INDICES
            macd_line = float(row[8]) if row[8] is not None else 0.0      # ✅ row[8] is macd
            macd_signal = float(row[9]) if row[9] is not None else 0.0    # ✅ row[9] is macd_signal
            macd_histogram = macd_line - macd_signal
            
            print(f"📈 {symbol} MACD Analysis:")
            print(f"   MACD Line (12-26 EMA): {macd_line:.4f}")
            print(f"   Signal Line (9 EMA): {macd_signal:.4f}")
            print(f"   Histogram (MACD-Signal): {macd_histogram:.4f}")
            print(f"   MACD Trend: {'BULLISH' if macd_histogram > 0 else 'BEARISH'}")
            print(f"   ✅ MACD Calculation: 12-EMA - 26-EMA = MACD Line")
            print(f"   ✅ Signal Line: 9-EMA of MACD Line")
            print(f"   ✅ Histogram: MACD Line - Signal Line")
            
            return {
                'date': row[0],
                'close': close_price,
                'open': open_price,
                'rsi_14': row[5],        # ✅ row[5] is rsi_14
                'sma_50': row[6],        # ✅ row[6] is sma_50
                'ema_20': ema_20,        # ✅ row[7] is ema_20
                'macd': macd_line,       # ✅ Using corrected macd_line
                'macd_signal': macd_signal,  # ✅ Using corrected macd_signal
                'macd_histogram': macd_histogram,
                'volume': current_volume,
                'low': low_price,
                'high': high_price,
                'avg_volume_20d': avg_volume_20d,
                'volume_ratio': current_volume/avg_volume_20d if avg_volume_20d > 0 else 0.0,
                'price_range': high_price - low_price,
                # Critical Analysis Results
                'trend_confirmation': trend_confirmation,
                'trend_confirmation_reason': trend_confirmation_reason,
                'volume_price_confirmation': volume_price_confirmation,
                'volume_price_reason': volume_price_reason,
                'price_action_bullish': price_action_bullish,
                'high_volume': high_volume,
                # Recovery Detection Data
                'relative_strength': relative_strength,
                'price_stability': price_stability,
                'stability_score': price_stability.get('stability_score', 0.0),
                'no_new_lows': price_stability.get('no_new_lows', False),
                'range_stable': price_stability.get('range_stable', False),
                'close_upper_half': price_stability.get('close_upper_half', False)
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
    
    print(f"🎯 Market Context for {symbol} on {target_date}:")
    print(f"   Volatility: {volatility:.2f}%")
    print(f"   Recent Change: {recent_change:.2f}%")
    print(f"   VIX Level: {vix_level:.2f}")
    print(f"   Asset Type: {asset_type}")
    
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
