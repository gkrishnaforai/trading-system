#!/usr/bin/env python3
"""
User-Friendly Signal Engine Display
Comprehensive market analysis for users
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import unified engine
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

def user_friendly_signal_display():
    """Display comprehensive signal analysis in user-friendly format"""
    
    print("🎯 TQQQ SIGNAL ENGINE - COMPREHENSIVE ANALYSIS")
    print("=" * 70)
    print("📈 Real-time Market Intelligence for Trading Decisions")
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
            print("❌ No data available")
            return
        
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
        ])
        df['date'] = pd.to_datetime(df['date'])
        
        # Initialize engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Get latest analysis
        latest_idx = len(df) - 1
        latest_row = df.iloc[latest_idx]
        
        # Calculate conditions
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
        
        signal_result = engine.generate_signal(conditions)
        
        # 🎯 SIGNAL SUMMARY CARD
        print("🎯 SIGNAL SUMMARY")
        print("=" * 40)
        
        signal_icon = "🟢" if signal_result.signal.value == "buy" else "🔴" if signal_result.signal.value == "sell" else "⚪"
        signal_action = "BUY" if signal_result.signal.value == "buy" else "SELL" if signal_result.signal.value == "sell" else "HOLD"
        
        print(f"{signal_icon} RECOMMENDATION: {signal_action}")
        print(f"📊 Price: ${latest_row['close']:.2f}")
        print(f"🎯 Confidence: {int(signal_result.confidence * 100)}%")
        print(f"📋 Market Regime: {signal_result.metadata.get('regime', 'unknown').replace('_', ' ').title()}")
        print()
        
        # 📈 MARKET STATUS
        print("📈 MARKET STATUS")
        print("=" * 40)
        
        trend_icon = "📈" if latest_row['ema_20'] > latest_row['sma_50'] else "📉" if latest_row['ema_20'] < latest_row['sma_50'] else "➡️"
        trend_text = "UPTREND" if latest_row['ema_20'] > latest_row['sma_50'] else "DOWNTREND" if latest_row['ema_20'] < latest_row['sma_50'] else "SIDEWAYS"
        
        print(f"{trend_icon} Trend: {trend_text}")
        print(f"💰 Price Change: {recent_change:+.2%}")
        print(f"📊 RSI: {latest_row['rsi']:.1f} ({get_rsi_status(latest_row['rsi'])})")
        print(f"📈 Volume: {latest_row['volume']:,}")
        print(f"⚡ Volatility: {volatility:.1f}% ({get_volatility_status(volatility)})")
        print()
        
        # 🧠 ENGINE ANALYSIS
        print("🧠 ENGINE ANALYSIS")
        print("=" * 40)
        
        for i, reason in enumerate(signal_result.reasoning, 1):
            print(f"  {i}. {reason}")
        print()
        
        # 📋 REGIME INSIGHTS
        print("📋 REGIME INSIGHTS")
        print("=" * 40)
        
        regime = signal_result.metadata.get('regime', 'unknown')
        regime_info = get_regime_info(regime)
        
        print(f"🔄 Current Regime: {regime_info['name']}")
        print(f"📝 Description: {regime_info['description']}")
        print(f"🎯 Focus: {regime_info['focus']}")
        print(f"💡 Best For: {regime_info['best_for']}")
        print()
        
        # ⚠️ RISK ANALYSIS
        print("⚠️ RISK ANALYSIS")
        print("=" * 40)
        
        risk_level = get_risk_level(volatility)
        risk_icon = "🔴" if risk_level == "HIGH" else "🟡" if risk_level == "MODERATE" else "🟢"
        
        print(f"{risk_icon} Risk Level: {risk_level}")
        print(f"📊 Volatility: {volatility:.1f}% ({'High' if volatility > 6 else 'Normal' if volatility > 4 else 'Low'})")
        print(f"💼 Position Size: {get_position_suggestion(signal_result.signal.value, volatility)}")
        print()
        
        # 🎯 TRADING PLAN
        print("🎯 TRADING PLAN")
        print("=" * 40)
        
        if signal_result.signal.value == "buy":
            print("🟢 ACTION PLAN:")
            print(f"  📊 Entry: ${latest_row['close']:.2f}")
            print(f"  🎯 Target: +5-10% over 5-7 days")
            print(f"  🛡️ Stop Loss: -3-5% from entry")
            print(f"  ⏰ Hold Time: 3-7 days")
            print(f"  💰 Risk/Reward: 1:2 to 1:3")
        elif signal_result.signal.value == "sell":
            print("🔴 ACTION PLAN:")
            print(f"  📊 Entry: ${latest_row['close']:.2f}")
            print(f"  🎯 Target: -5-10% over 3-5 days")
            print(f"  🛡️ Stop Loss: +3% from entry")
            print(f"  ⏰ Hold Time: 2-5 days")
            print(f"  💰 Risk/Reward: 1:2 to 1:3")
        else:
            print("⚪ ACTION PLAN:")
            print(f"  📊 Current: ${latest_row['close']:.2f}")
            print(f"  🎯 Strategy: Wait for better entry")
            print(f"  🛡️ Risk: Low - stay in cash")
            print(f"  ⏰ Monitor: Daily for signal changes")
            print(f"  💰 Position: Hold cash")
        
        print()
        
        # 🔍 KEY LEVELS
        print("🔍 KEY LEVELS TO WATCH")
        print("=" * 40)
        
        print(f"📈 Resistance: ${latest_row['high']:.2f}")
        print(f"📉 Support: ${latest_row['low']:.2f}")
        print(f"📊 SMA20: ${latest_row['ema_20']:.2f}")
        print(f"📊 SMA50: ${latest_row['sma_50']:.2f}")
        
        if latest_row['rsi'] > 70:
            print(f"⚠️ RSI Overbought: >70 (Current: {latest_row['rsi']:.1f})")
        elif latest_row['rsi'] < 30:
            print(f"💡 RSI Oversold: <30 (Current: {latest_row['rsi']:.1f})")
        else:
            print(f"📊 RSI Neutral: 30-70 (Current: {latest_row['rsi']:.1f})")
        
        print()
        
        # 📊 PERFORMANCE TRACK RECORD
        print("📊 PERFORMANCE TRACK RECORD (2025)")
        print("=" * 40)
        
        # Calculate historical performance
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
            buy_signals = hist_df[hist_df['signal'] == 'buy']
            if len(buy_signals) > 0:
                avg_return = buy_signals['return_5d'].mean()
                win_rate = (buy_signals['return_5d'] > 0).mean() * 100
                
                print(f"🟢 BUY Signals: {len(buy_signals)} total")
                print(f"  📈 Average Return: {avg_return:+.2%}")
                print(f"  🎯 Win Rate: {win_rate:.1f}%")
                print(f"  💰 Success Rate: {'Excellent' if win_rate > 70 else 'Good' if win_rate > 60 else 'Fair' if win_rate > 50 else 'Poor'}")
            
            # Current regime performance
            current_regime_signals = hist_df[hist_df['regime'] == regime]
            if len(current_regime_signals) > 0:
                regime_buy_signals = current_regime_signals[current_regime_signals['signal'] == 'buy']
                if len(regime_buy_signals) > 0:
                    regime_avg_return = regime_buy_signals['return_5d'].mean()
                    regime_win_rate = (regime_buy_signals['return_5d'] > 0).mean() * 100
                    print(f"📋 Current Regime ({regime}):")
                    print(f"  🟢 BUY Signals: {len(regime_buy_signals)}")
                    print(f"  📈 Average Return: {regime_avg_return:+.2%}")
                    print(f"  🎯 Win Rate: {regime_win_rate:.1f}%")
        
        print()
        
        # 🌍 MARKET CONTEXT
        print("🌍 MARKET CONTEXT")
        print("=" * 40)
        
        recent_5_days = df.iloc[-5:]
        recent_change_5d = (recent_5_days['close'].iloc[-1] / recent_5_days['close'].iloc[0] - 1) * 100
        recent_volatility = recent_5_days['close'].pct_change().std() * 100
        avg_volume = df['volume'].mean()
        volume_ratio = latest_row['volume'] / avg_volume
        
        print(f"📅 Last 5 Days: {recent_change_5d:+.1f}%")
        print(f"⚡ Recent Volatility: {recent_volatility:.1f}%")
        print(f"📊 Volume Ratio: {volume_ratio:.1f}x average")
        
        if volume_ratio > 1.5:
            print(f"📈 High volume - Strong conviction")
        elif volume_ratio < 0.5:
            print(f"📉 Low volume - Weak conviction")
        else:
            print(f"📊 Normal volume")
        
        print()
        
        # 💡 QUICK TAKEAWAYS
        print("💡 QUICK TAKEAWAYS")
        print("=" * 40)
        
        takeaways = []
        
        if signal_result.signal.value == "buy":
            takeaways.append("🟢 Engine detects buying opportunity")
            takeaways.append(f"📊 Based on {regime.replace('_', ' ')} regime")
            takeaways.append(f"🎯 {int(signal_result.confidence * 100)}% confidence level")
        elif signal_result.signal.value == "sell":
            takeaways.append("🔴 Engine detects selling opportunity")
            takeaways.append(f"📊 Based on {regime.replace('_', ' ')} regime")
            takeaways.append(f"🎯 {int(signal_result.confidence * 100)}% confidence level")
        else:
            takeaways.append("⚪ Engine recommends waiting")
            takeaways.append("📊 No clear trading setup")
            takeaways.append("🎯 Monitor for better entry")
        
        if volatility > 6:
            takeaways.append("⚠️ High volatility - be cautious")
        elif volatility < 3:
            takeaways.append("✅ Low volatility - stable conditions")
        
        for takeaway in takeaways:
            print(f"  {takeaway}")
        
        print()
        
        # 📞 NEXT STEPS
        print("📞 NEXT STEPS")
        print("=" * 40)
        
        if signal_result.signal.value == "buy":
            print("1. 📊 Consider entering BUY position")
            print("2. 🛡️ Set stop loss at 3-5% below entry")
            print("3. 🎯 Target 5-10% gain over 5-7 days")
            print("4. 📈 Monitor daily for signal changes")
            print("5. 💰 Position size based on risk level")
        elif signal_result.signal.value == "sell":
            print("1. 📊 Consider SELL or SHORT position")
            print("2. 🛡️ Set stop loss at 3% above entry")
            print("3. 🎯 Target 5-10% decline over 3-5 days")
            print("4. 📈 Monitor daily for signal changes")
            print("5. 💰 Use smaller position in volatile conditions")
        else:
            print("1. ⚪ Stay in cash or HOLD current position")
            print("2. 📊 Monitor for signal changes")
            print("3. 🎯 Wait for better entry point")
            print("4. 📈 Review market conditions daily")
            print("5. 💰 Preserve capital for better opportunities")
        
        print()
        print("⚠️ DISCLAIMER: This analysis is for educational purposes only. Always do your own research before trading.")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

def get_rsi_status(rsi):
    if rsi < 30:
        return "OVERSOLD"
    elif rsi > 70:
        return "OVERBOUGHT"
    else:
        return "NEUTRAL"

def get_volatility_status(volatility):
    if volatility > 6:
        return "HIGH"
    elif volatility > 4:
        return "NORMAL"
    else:
        return "LOW"

def get_regime_info(regime):
    regimes = {
        "mean_reversion": {
            "name": "Mean Reversion",
            "description": "Market reverting to average levels",
            "focus": "Oversold/overbought reversals",
            "best_for": "Range-bound markets"
        },
        "trend_continuation": {
            "name": "Trend Continuation",
            "description": "Market in established trend",
            "focus": "Pullback entries",
            "best_for": "Momentum trading"
        },
        "breakout": {
            "name": "Breakout",
            "description": "Momentum expansion phase",
            "focus": "Breakout continuation",
            "best_for": "Volatility trading"
        },
        "volatility_expansion": {
            "name": "Volatility Expansion",
            "description": "High volatility risk-off",
            "focus": "Capital preservation",
            "best_for": "Risk management"
        }
    }
    return regimes.get(regime, {"name": "Unknown", "description": "N/A", "focus": "N/A", "best_for": "N/A"})

def get_risk_level(volatility):
    if volatility > 6:
        return "HIGH"
    elif volatility > 4:
        return "MODERATE"
    else:
        return "LOW"

def get_position_suggestion(signal, volatility):
    if signal == "buy":
        if volatility > 6:
            return "SMALL (25%)"
        elif volatility > 4:
            return "MEDIUM (50%)"
        else:
            return "LARGE (75%)"
    elif signal == "sell":
        return "EXIT POSITION"
    else:
        return "HOLD CASH"

if __name__ == "__main__":
    user_friendly_signal_display()
