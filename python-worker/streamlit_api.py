#!/usr/bin/env python3
"""
Streamlit-Friendly API for TQQQ Signal Engine
Comprehensive analysis endpoint for Streamlit integration
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
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

router = APIRouter()

class StreamlitSignalRequest(BaseModel):
    symbol: str = "TQQQ"
    date: Optional[str] = None  # If None, use latest data
    include_historical: bool = True
    include_performance: bool = True

class StreamlitSignalResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/api/streamlit/signal-analysis", response_model=StreamlitSignalResponse)
async def streamlit_signal_analysis(request: StreamlitSignalRequest):
    """
    Streamlit-friendly signal analysis endpoint
    Returns comprehensive analysis in JSON format for easy frontend consumption
    """
    
    try:
        # Load data
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Build query
        if request.date:
            date_filter = f"AND i.date = '{request.date}'"
        else:
            date_filter = "AND i.date >= '2025-01-01' AND i.date <= '2025-12-31'"
        
        cursor.execute(f"""
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = '{request.symbol}' 
            {date_filter}
            ORDER BY i.date
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            return StreamlitSignalResponse(
                success=False,
                error=f"No data found for {request.symbol} on {request.date or '2025'}"
            )
        
        df = pd.DataFrame(rows, columns=[
            'date', 'close', 'rsi', 'sma_50', 'ema_20', 'macd', 'macd_signal', 'volume', 'low', 'high'
        ])
        df['date'] = pd.to_datetime(df['date'])
        
        # Initialize unified engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Get target row
        if request.date:
            target_date = pd.to_datetime(request.date)
            target_row = df[df['date'] == target_date]
            if len(target_row) == 0:
                return StreamlitSignalResponse(
                    success=False,
                    error=f"No data found for {request.symbol} on {request.date}"
                )
            target_row = target_row.iloc[0]
            target_idx = df.index.get_loc(df[df['date'] == target_date].index[0])
        else:
            target_idx = len(df) - 1
            target_row = df.iloc[target_idx]
        
        # Calculate market conditions
        if target_idx >= 2:
            recent_close = df.iloc[target_idx-2]['close']
            recent_change = (target_row['close'] - recent_close) / recent_close
            
            start_idx = max(0, target_idx - 19)
            volatility_data = df.iloc[start_idx:target_idx+1]['close'].pct_change().dropna()
            volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
            
            conditions = MarketConditions(
                rsi=target_row['rsi'],
                sma_20=target_row['ema_20'],
                sma_50=target_row['sma_50'],
                ema_20=target_row['ema_20'],
                current_price=target_row['close'],
                recent_change=recent_change,
                macd=target_row['macd'],
                macd_signal=target_row['macd_signal'],
                volatility=volatility
            )
            
            # Generate signal
            signal_result = engine.generate_signal(conditions)
            
            # Build Streamlit-friendly response
            response_data = {
                "timestamp": datetime.now().isoformat(),
                "symbol": request.symbol,
                "analysis_date": target_row['date'].strftime('%Y-%m-%d'),
                
                # Signal Summary (for main display)
                "signal_summary": {
                    "signal": signal_result.signal.value.upper(),
                    "confidence": round(signal_result.confidence, 2),
                    "confidence_percent": int(signal_result.confidence * 100),
                    "regime": signal_result.metadata.get('regime', 'unknown').replace('_', ' ').title(),
                    "price": round(target_row['close'], 2),
                    "daily_change": round(recent_change * 100, 2),
                    "reasoning": signal_result.reasoning
                },
                
                # Market Overview (for status cards)
                "market_overview": {
                    "price": round(target_row['close'], 2),
                    "daily_change": round(recent_change * 100, 2),
                    "daily_change_percent": f"{recent_change:+.2%}",
                    "volume": int(target_row['volume']),
                    "volume_formatted": f"{target_row['volume']:,}",
                    "volatility": round(volatility, 1),
                    "volatility_status": "High" if volatility > 6 else "Normal" if volatility > 4 else "Low"
                },
                
                # Technical Indicators (for charts and indicators)
                "technical_indicators": {
                    "rsi": round(target_row['rsi'], 1),
                    "rsi_status": "OVERSOLD" if target_row['rsi'] < 35 else "OVERBOUGHT" if target_row['rsi'] > 70 else "NEUTRAL",
                    "sma20": round(target_row['ema_20'], 2),
                    "sma50": round(target_row['sma_50'], 2),
                    "trend": "UPTREND" if target_row['ema_20'] > target_row['sma_50'] else "DOWNTREND" if target_row['ema_20'] < target_row['sma_50'] else "SIDEWAYS",
                    "price_vs_sma20": "ABOVE" if target_row['close'] > target_row['ema_20'] else "BELOW",
                    "price_vs_sma50": "ABOVE" if target_row['close'] > target_row['sma_50'] else "BELOW",
                    "macd": round(target_row['macd'], 3),
                    "macd_signal": round(target_row['macd_signal'], 3),
                    "macd_histogram": round(target_row['macd'] - target_row['macd_signal'], 3)
                },
                
                # Risk Assessment (for risk management)
                "risk_assessment": {
                    "risk_level": "HIGH" if volatility > 6 else "MODERATE" if volatility > 4 else "LOW",
                    "risk_color": "red" if volatility > 6 else "orange" if volatility > 4 else "green",
                    "volatility": round(volatility, 1),
                    "suggested_position": get_position_suggestion(signal_result.signal.value, volatility),
                    "position_size_percent": get_position_size_percent(signal_result.signal.value, volatility)
                },
                
                # Key Levels (for chart annotations)
                "key_levels": {
                    "resistance": round(target_row['high'], 2),
                    "support": round(target_row['low'], 2),
                    "sma20": round(target_row['ema_20'], 2),
                    "sma50": round(target_row['sma_50'], 2),
                    "current_price": round(target_row['close'], 2),
                    "rsi_oversold": 30,
                    "rsi_overbought": 70,
                    "current_rsi": round(target_row['rsi'], 1)
                },
                
                # Trading Plan (for action items)
                "trading_plan": {
                    "action": get_trading_action(signal_result.signal.value),
                    "entry_price": round(target_row['close'], 2),
                    "target_return": get_target_return(signal_result.signal.value),
                    "stop_loss": get_stop_loss(signal_result.signal.value),
                    "hold_time": get_hold_time(signal_result.signal.value),
                    "risk_reward": get_risk_reward(signal_result.signal.value)
                },
                
                # Regime Information (for educational content)
                "regime_info": {
                    "name": signal_result.metadata.get('regime', 'unknown').replace('_', ' ').title(),
                    "description": get_regime_description(signal_result.metadata.get('regime', 'unknown')),
                    "focus": get_regime_focus(signal_result.metadata.get('regime', 'unknown')),
                    "best_for": get_regime_best_for(signal_result.metadata.get('regime', 'unknown'))
                }
            }
            
            # Add historical performance if requested
            if request.include_performance:
                response_data["historical_performance"] = get_historical_performance_data(df, engine, signal_result.metadata.get('regime', 'unknown'))
            
            # Add historical data if requested
            if request.include_historical:
                response_data["historical_data"] = get_historical_data_for_chart(df, target_idx)
            
            return StreamlitSignalResponse(
                success=True,
                data=response_data
            )
        
        else:
            return StreamlitSignalResponse(
                success=False,
                error="Insufficient data for analysis"
            )
        
    except Exception as e:
        return StreamlitSignalResponse(
            success=False,
            error=str(e)
        )
    finally:
        if 'conn' in locals():
            conn.close()

def get_position_suggestion(signal: str, volatility: float) -> str:
    """Get position sizing suggestion"""
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

def get_position_size_percent(signal: str, volatility: float) -> int:
    """Get position size as percentage"""
    if signal == "buy":
        if volatility > 6:
            return 25
        elif volatility > 4:
            return 50
        else:
            return 75
    elif signal == "sell":
        return 0
    else:
        return 0

def get_trading_action(signal: str) -> str:
    """Get trading action"""
    if signal == "buy":
        return "BUY"
    elif signal == "sell":
        return "SELL"
    else:
        return "HOLD"

def get_target_return(signal: str) -> str:
    """Get target return"""
    if signal == "buy":
        return "+5-10%"
    elif signal == "sell":
        return "-5-10%"
    else:
        return "Wait for setup"

def get_stop_loss(signal: str) -> str:
    """Get stop loss"""
    if signal == "buy":
        return "-3-5%"
    elif signal == "sell":
        return "+3%"
    else:
        return "Low risk"

def get_hold_time(signal: str) -> str:
    """Get hold time"""
    if signal == "buy":
        return "3-7 days"
    elif signal == "sell":
        return "2-5 days"
    else:
        return "Monitor daily"

def get_risk_reward(signal: str) -> str:
    """Get risk/reward ratio"""
    if signal in ["buy", "sell"]:
        return "1:2 to 1:3"
    else:
        return "Preserve capital"

def get_regime_description(regime: str) -> str:
    """Get regime description"""
    descriptions = {
        "mean_reversion": "Market is showing signs of reverting to average levels",
        "trend_continuation": "Market is in established trend with momentum",
        "breakout": "Market showing momentum expansion and breakout patterns",
        "volatility_expansion": "High volatility detected - risk-off mode"
    }
    return descriptions.get(regime, "Unknown regime")

def get_regime_focus(regime: str) -> str:
    """Get regime focus"""
    focuses = {
        "mean_reversion": "Oversold/overbought reversals",
        "trend_continuation": "Pullback entries in trend",
        "breakout": "Momentum continuation plays",
        "volatility_expansion": "Capital preservation"
    }
    return focuses.get(regime, "Unknown focus")

def get_regime_best_for(regime: str) -> str:
    """Get regime best for"""
    best_for = {
        "mean_reversion": "Range-bound markets, pullback plays",
        "trend_continuation": "Momentum stocks, strong trends",
        "breakout": "Volatile breakouts, momentum trading",
        "volatility_expansion": "Risk management, defensive positions"
    }
    return best_for.get(regime, "Unknown application")

def get_historical_performance_data(df: pd.DataFrame, engine: UnifiedTQQQSwingEngine, current_regime: str) -> Dict[str, Any]:
    """Get historical performance data"""
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
            
            conditions = MarketConditions(
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
            
            signal = engine.generate_signal(conditions)
            
            if pos < len(df) - 5:
                future_price = df.iloc[pos + 5]['close']
                return_5d = (future_price - row['close']) / row['close']
            else:
                return_5d = 0
            
            historical_signals.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'signal': signal.signal.value,
                'return_5d': return_5d,
                'regime': signal.metadata.get('regime', 'unknown'),
                'confidence': signal.confidence
            })
            
        except Exception:
            continue
    
    hist_df = pd.DataFrame(historical_signals)
    
    if len(hist_df) > 0:
        # Overall stats
        buy_signals = hist_df[hist_df['signal'] == 'buy']
        sell_signals = hist_df[hist_df['signal'] == 'sell']
        hold_signals = hist_df[hist_df['signal'] == 'hold']
        
        result = {
            "total_signals": len(hist_df),
            "buy_signals": {
                "count": len(buy_signals),
                "avg_return": round(buy_signals['return_5d'].mean(), 4) if len(buy_signals) > 0 else 0,
                "win_rate": round((buy_signals['return_5d'] > 0).mean() * 100, 1) if len(buy_signals) > 0 else 0,
                "success_rate": get_success_rating((buy_signals['return_5d'] > 0).mean() * 100) if len(buy_signals) > 0 else "No data"
            },
            "sell_signals": {
                "count": len(sell_signals),
                "avg_return": round(sell_signals['return_5d'].mean(), 4) if len(sell_signals) > 0 else 0,
                "win_rate": round((sell_signals['return_5d'] < 0).mean() * 100, 1) if len(sell_signals) > 0 else 0,
                "success_rate": get_success_rating((sell_signals['return_5d'] < 0).mean() * 100) if len(sell_signals) > 0 else "No data"
            },
            "hold_signals": {
                "count": len(hold_signals),
                "avg_return": round(hold_signals['return_5d'].mean(), 4) if len(hold_signals) > 0 else 0,
                "win_rate": round((hold_signals['return_5d'] > 0).mean() * 100, 1) if len(hold_signals) > 0 else 0,
                "success_rate": get_success_rating((hold_signals['return_5d'] > 0).mean() * 100) if len(hold_signals) > 0 else "No data"
            }
        }
        
        # Current regime performance
        current_regime_signals = hist_df[hist_df['regime'] == current_regime]
        if len(current_regime_signals) > 0:
            regime_buy_signals = current_regime_signals[current_regime_signals['signal'] == 'buy']
            if len(regime_buy_signals) > 0:
                result["current_regime"] = {
                    "name": current_regime,
                    "buy_signals": len(regime_buy_signals),
                    "avg_return": round(regime_buy_signals['return_5d'].mean(), 4),
                    "win_rate": round((regime_buy_signals['return_5d'] > 0).mean() * 100, 1),
                    "success_rate": get_success_rating((regime_buy_signals['return_5d'] > 0).mean() * 100)
                }
        
        # Recent performance (last 30 signals)
        recent_signals = hist_df.tail(30)
        if len(recent_signals) > 0:
            recent_buy = recent_signals[recent_signals['signal'] == 'buy']
            result["recent_performance"] = {
                "period": "Last 30 signals",
                "buy_signals": len(recent_buy),
                "avg_return": round(recent_buy['return_5d'].mean(), 4) if len(recent_buy) > 0 else 0,
                "win_rate": round((recent_buy['return_5d'] > 0).mean() * 100, 1) if len(recent_buy) > 0 else 0
            }
        
        return result
    
    return {"message": "Insufficient historical data"}

def get_success_rating(win_rate: float) -> str:
    """Get success rating based on win rate"""
    if win_rate >= 70:
        return "Excellent"
    elif win_rate >= 60:
        return "Good"
    elif win_rate >= 50:
        return "Fair"
    else:
        return "Poor"

def get_historical_data_for_chart(df: pd.DataFrame, target_idx: int) -> Dict[str, Any]:
    """Get historical data for charting"""
    # Get last 60 days of data
    start_idx = max(0, target_idx - 59)
    chart_data = df.iloc[start_idx:target_idx+1]
    
    return {
        "dates": [date.strftime('%Y-%m-%d') for date in chart_data['date']],
        "prices": [round(price, 2) for price in chart_data['close']],
        "rsi": [round(rsi, 1) for rsi in chart_data['rsi']],
        "sma20": [round(sma, 2) for sma in chart_data['ema_20']],
        "sma50": [round(sma, 2) for sma in chart_data['sma_50']],
        "volume": [int(vol) for vol in chart_data['volume']],
        "high": [round(high, 2) for high in chart_data['high']],
        "low": [round(low, 2) for low in chart_data['low']]
    }
