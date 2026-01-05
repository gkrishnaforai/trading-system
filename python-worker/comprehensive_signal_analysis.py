#!/usr/bin/env python3
"""
Comprehensive Signal Engine Analysis
Full market understanding for users with detailed explanations
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

def comprehensive_signal_analysis():
    """Provide comprehensive signal analysis with full market understanding"""
    
    print("🎯 COMPREHENSIVE TQQQ SIGNAL ENGINE ANALYSIS")
    print("=" * 70)
    print("Full Market Understanding for Trading Decisions")
    print()
    
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
        
        print(f"📊 DATA OVERVIEW:")
        print("-" * 30)
        print(f"  Period: 2025-01-01 to 2025-12-31")
        print(f"  Trading Days: {len(df)}")
        print(f"  Price Range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")
        print(f"  Current Price: ${df['close'].iloc[-1]:.2f}")
        print(f"  Year-to-Date: {((df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100):+.1f}%")
        print()
        
        # Initialize unified engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Get latest signal
        latest_idx = len(df) - 1
        if latest_idx < 10:
            print("❌ Insufficient data for analysis")
            return
        
        # Calculate market conditions for latest day
        latest_row = df.iloc[latest_idx]
        recent_close = df.iloc[latest_idx-2]['close']
        recent_change = (latest_row['close'] - recent_close) / recent_close
        
        start_idx = max(0, latest_idx - 19)
        volatility_data = df.iloc[start_idx:latest_idx+1]['close'].pct_change().dropna()
        volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
        
        conditions = MarketConditions(
            rsi=latest_row['rsi'],
            sma_20=latest_row['ema_20'],
            sma_50=latest_row['sma_50'],
            ema_20=latest_row['ema_20'],
            current_price=latest_row['close'],
            recent_change=recent_change,
            macd=latest_row['macd'],
            macd_signal=latest_row['macd_signal'],
            volatility=volatility
        )
        
        # Generate latest signal
        signal_result = engine.generate_signal(conditions)
        
        print(f"🎯 LATEST SIGNAL ANALYSIS")
        print("=" * 50)
        print(f"Analysis Date: {latest_row['date'].strftime('%Y-%m-%d')}")
        print()
        
        # Market Overview
        print(f"📈 MARKET OVERVIEW:")
        print("-" * 30)
        print(f"  TQQQ Price: ${latest_row['close']:.2f}")
        print(f"  Daily Change: {recent_change:+.2%}")
        print(f"  Volume: {latest_row['volume']:,}")
        print(f"  Volatility: {volatility:.1f}%")
        print()
        
        # Technical Indicators
        print(f"📊 TECHNICAL INDICATORS:")
        print("-" * 30)
        print(f"  RSI (14): {latest_row['rsi']:.1f}")
        rsi_status = "OVERSOLD" if latest_row['rsi'] < 35 else "OVERBOUGHT" if latest_row['rsi'] > 70 else "NEUTRAL"
        print(f"  RSI Status: {rsi_status}")
        print(f"  SMA20: ${latest_row['ema_20']:.2f}")
        print(f"  SMA50: ${latest_row['sma_50']:.2f}")
        
        # Trend analysis
        if latest_row['ema_20'] > latest_row['sma_50']:
            trend = "UPTREND"
            trend_icon = "📈"
        elif latest_row['ema_20'] < latest_row['sma_50']:
            trend = "DOWNTREND"
            trend_icon = "📉"
        else:
            trend = "SIDEWAYS"
            trend_icon = "➡️"
        
        print(f"  Trend: {trend_icon} {trend}")
        
        # Price vs moving averages
        if latest_row['close'] > latest_row['ema_20']:
            price_vs_sma20 = "ABOVE"
        else:
            price_vs_sma20 = "BELOW"
        
        if latest_row['close'] > latest_row['sma_50']:
            price_vs_sma50 = "ABOVE"
        else:
            price_vs_sma50 = "BELOW"
        
        print(f"  Price vs SMA20: {price_vs_sma20}")
        print(f"  Price vs SMA50: {price_vs_sma50}")
        print()
        
        # Signal Details
        print(f"🎯 SIGNAL DETAILS:")
        print("-" * 30)
        
        signal_icon = "🟢" if signal_result.signal.value == "buy" else "🔴" if signal_result.signal.value == "sell" else "⚪"
        print(f"  Signal: {signal_icon} {signal_result.signal.value.upper()}")
        print(f"  Confidence: {signal_result.confidence:.2f}")
        print(f"  Regime: {signal_result.metadata.get('regime', 'unknown').replace('_', ' ').title()}")
        print()
        
        # Detailed Reasoning
        print(f"🧠 ENGINE REASONING:")
        print("-" * 30)
        for i, reason in enumerate(signal_result.reasoning, 1):
            print(f"  {i}. {reason}")
        print()
        
        # Market Regime Explanation
        regime = signal_result.metadata.get('regime', 'unknown')
        print(f"📋 MARKET REGIME EXPLANATION:")
        print("-" * 30)
        
        if regime == "mean_reversion":
            print(f"  🔄 Mean Reversion Regime")
            print(f"     Market is showing signs of reverting to average")
            print(f"     Focus on oversold/overbought levels for reversals")
            print(f"     Best for: Range-bound markets, pullback plays")
        elif regime == "trend_continuation":
            print(f"  📈 Trend Continuation Regime")
            print(f"     Market is in established uptrend")
            print(f"     Focus on pullbacks to trend lines")
            print(f"     Best for: Momentum stocks, strong trends")
        elif regime == "breakout":
            print(f"  🚀 Breakout Regime")
            print(f"     Market showing momentum expansion")
            print(f"     Focus on momentum continuation")
            print(f"     Best for: Volatile breakouts, momentum plays")
        elif regime == "volatility_expansion":
            print(f"  ⚠️ Volatility Expansion Regime")
            print(f"     High volatility detected - risk-off mode")
            print(f"     Focus on capital preservation")
            print(f"     Best for: Risk management, defensive positions")
        print()
        
        # Risk Assessment
        print(f"⚠️ RISK ASSESSMENT:")
        print("-" * 30)
        
        # Risk level based on volatility and signal
        if volatility > 6:
            risk_level = "HIGH"
            risk_icon = "🔴"
        elif volatility > 4:
            risk_level = "MODERATE"
            risk_icon = "🟡"
        else:
            risk_level = "LOW"
            risk_icon = "🟢"
        
        print(f"  Risk Level: {risk_icon} {risk_level}")
        print(f"  Volatility: {volatility:.1f}% ({'High' if volatility > 6 else 'Normal' if volatility > 4 else 'Low'})")
        
        # Position sizing suggestion
        if signal_result.signal.value == "buy":
            if volatility > 6:
                position_size = "SMALL (25%)"
            elif volatility > 4:
                position_size = "MEDIUM (50%)"
            else:
                position_size = "LARGE (75%)"
        elif signal_result.signal.value == "sell":
            position_size = "EXIT POSITION"
        else:
            position_size = "HOLD CASH"
        
        print(f"  Suggested Position: {position_size}")
        print()
        
        # Historical Performance
        print(f"📊 HISTORICAL PERFORMANCE (2025):")
        print("-" * 30)
        
        # Generate signals for historical analysis
        historical_signals = []
        
        for idx, row in df.iterrows():
            pos = df.index.get_loc(idx)
            if pos < 10:
                continue
            
            try:
                recent_close = df.iloc[pos-2]['close']
                recent_change = (row['close'] - recent_close) / recent_close
                
                start_idx = max(0, pos - 19)
                volatility_data = df.iloc[start_idx:pos+1]['close'].pct_change().dropna()
                vol = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
                
                hist_conditions = MarketConditions(
                    rsi=row['rsi'],
                    sma_20=row['ema_20'],
                    sma_50=row['sma_50'],
                    ema_20=row['ema_20'],
                    current_price=row['close'],
                    recent_change=recent_change,
                    macd=row['macd'],
                    macd_signal=row['macd_signal'],
                    volatility=vol
                )
                
                hist_signal = engine.generate_signal(hist_conditions)
                
                # Calculate 5-day return if available
                if pos < len(df) - 5:
                    future_price = df.iloc[pos + 5]['close']
                    return_5d = (future_price - row['close']) / row['close']
                else:
                    return_5d = 0
                
                historical_signals.append({
                    'signal': hist_signal.signal.value,
                    'return_5d': return_5d,
                    'regime': hist_signal.metadata.get('regime', 'unknown')
                })
                
            except Exception:
                continue
        
        hist_df = pd.DataFrame(historical_signals)
        
        if len(hist_df) > 0:
            # Overall performance
            buy_signals = hist_df[hist_df['signal'] == 'buy']
            if len(buy_signals) > 0:
                avg_buy_return = buy_signals['return_5d'].mean()
                buy_win_rate = (buy_signals['return_5d'] > 0).mean() * 100
                print(f"  BUY Signals: {len(buy_signals)} total")
                print(f"    Avg Return (5d): {avg_buy_return:+.2%}")
                print(f"    Win Rate: {buy_win_rate:.1f}%")
            
            # Current regime performance
            current_regime_signals = hist_df[hist_df['regime'] == regime]
            if len(current_regime_signals) > 0:
                regime_buy_signals = current_regime_signals[current_regime_signals['signal'] == 'buy']
                if len(regime_buy_signals) > 0:
                    regime_avg_return = regime_buy_signals['return_5d'].mean()
                    regime_win_rate = (regime_buy_signals['return_5d'] > 0).mean() * 100
                    print(f"  Current Regime ({regime}): {len(regime_buy_signals)} BUY signals")
                    print(f"    Avg Return (5d): {regime_avg_return:+.2%}")
                    print(f"    Win Rate: {regime_win_rate:.1f}%")
        
        print()
        
        # Trading Recommendations
        print(f"💡 TRADING RECOMMENDATIONS:")
        print("-" * 30)
        
        if signal_result.signal.value == "buy":
            print(f"  🟢 ACTION: Consider BUY position")
            print(f"  📊 Entry: ${latest_row['close']:.2f}")
            print(f"  🎯 Target: +5-10% over 5-7 days")
            print(f"  🛡️ Stop Loss: -3-5% from entry")
            print(f"  ⏰ Hold Time: 3-7 days")
        elif signal_result.signal.value == "sell":
            print(f"  🔴 ACTION: Consider SELL or SHORT")
            print(f"  📊 Entry: ${latest_row['close']:.2f}")
            print(f"  🎯 Target: -5-10% over 3-5 days")
            print(f"  🛡️ Stop Loss: +3% from entry")
            print(f"  ⏰ Hold Time: 2-5 days")
        else:
            print(f"  ⚪ ACTION: HOLD or WAIT")
            print(f"  📊 Current: ${latest_row['close']:.2f}")
            print(f"  🎯 Wait for: Better entry point")
            print(f"  🛡️ Risk: Low")
            print(f"  ⏰ Monitor: Daily for signal changes")
        
        print()
        
        # Key Levels to Watch
        print(f"🔍 KEY LEVELS TO WATCH:")
        print("-" * 30)
        print(f"  Resistance: ${latest_row['high']:.2f}")
        print(f"  Support: ${latest_row['low']:.2f}")
        print(f"  SMA20: ${latest_row['ema_20']:.2f}")
        print(f"  SMA50: ${latest_row['sma_50']:.2f}")
        
        # RSI levels
        if latest_row['rsi'] > 70:
            print(f"  RSI Overbought: >70 (Current: {latest_row['rsi']:.1f})")
        elif latest_row['rsi'] < 30:
            print(f"  RSI Oversold: <30 (Current: {latest_row['rsi']:.1f})")
        else:
            print(f"  RSI Neutral: 30-70 (Current: {latest_row['rsi']:.1f})")
        
        print()
        
        # Market Context
        print(f"🌍 MARKET CONTEXT:")
        print("-" * 30)
        
        # Recent performance
        recent_5_days = df.iloc[-5:]
        recent_change_5d = (recent_5_days['close'].iloc[-1] / recent_5_days['close'].iloc[0] - 1) * 100
        print(f"  Last 5 Days: {recent_change_5d:+.1f}%")
        
        # Recent volatility
        recent_volatility = recent_5_days['close'].pct_change().std() * 100
        print(f"  Recent Volatility: {recent_volatility:.1f}%")
        
        # Volume analysis
        avg_volume = df['volume'].mean()
        volume_ratio = latest_row['volume'] / avg_volume
        print(f"  Volume Ratio: {volume_ratio:.1f}x average")
        
        if volume_ratio > 1.5:
            print(f"  📈 High volume detected - strong conviction")
        elif volume_ratio < 0.5:
            print(f"  📉 Low volume detected - weak conviction")
        else:
            print(f"  📊 Normal volume")
        
        print()
        
        # Disclaimer
        print(f"⚠️ DISCLAIMER:")
        print("-" * 30)
        print(f"  • This analysis is for educational purposes only")
        print(f"  • Past performance does not guarantee future results")
        print(f"  • Always do your own research before trading")
        print(f"  • Consider your risk tolerance and financial situation")
        print(f"  • Never risk more than you can afford to lose")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    comprehensive_signal_analysis()
