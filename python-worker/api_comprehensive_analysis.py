#!/usr/bin/env python3
"""
API Endpoint for Comprehensive Signal Analysis
User-friendly signal engine with full market understanding
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
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

class SignalAnalysisRequest(BaseModel):
    symbol: str = "TQQQ"
    date: Optional[str] = None  # If None, use latest data

class SignalAnalysisResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/signal/comprehensive-analysis", response_model=SignalAnalysisResponse)
async def comprehensive_signal_analysis_api(request: SignalAnalysisRequest):
    """
    Comprehensive signal analysis with full market understanding
    """
    
    try:
        # Load data
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Build query based on date
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
            return SignalAnalysisResponse(
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
        
        # Get target row (latest or specific date)
        if request.date:
            target_date = pd.to_datetime(request.date)
            target_row = df[df['date'] == target_date]
            if len(target_row) == 0:
                return SignalAnalysisResponse(
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
            
            # Build comprehensive response
            response_data = {
                "analysis_date": target_row['date'].strftime('%Y-%m-%d'),
                "symbol": request.symbol,
                "market_overview": {
                    "price": round(target_row['close'], 2),
                    "daily_change": f"{recent_change:+.2%}",
                    "volume": f"{target_row['volume']:,}",
                    "volatility": round(volatility, 1)
                },
                "technical_indicators": {
                    "rsi": round(target_row['rsi'], 1),
                    "rsi_status": "OVERSOLD" if target_row['rsi'] < 35 else "OVERBOUGHT" if target_row['rsi'] > 70 else "NEUTRAL",
                    "sma20": round(target_row['ema_20'], 2),
                    "sma50": round(target_row['sma_50'], 2),
                    "trend": "UPTREND" if target_row['ema_20'] > target_row['sma_50'] else "DOWNTREND" if target_row['ema_20'] < target_row['sma_50'] else "SIDEWAYS",
                    "price_vs_sma20": "ABOVE" if target_row['close'] > target_row['ema_20'] else "BELOW",
                    "price_vs_sma50": "ABOVE" if target_row['close'] > target_row['sma_50'] else "BELOW"
                },
                "signal_details": {
                    "signal": signal_result.signal.value.upper(),
                    "confidence": round(signal_result.confidence, 2),
                    "regime": signal_result.metadata.get('regime', 'unknown').replace('_', ' ').title(),
                    "reasoning": signal_result.reasoning
                },
                "regime_explanation": get_regime_explanation(signal_result.metadata.get('regime', 'unknown')),
                "risk_assessment": {
                    "risk_level": get_risk_level(volatility),
                    "volatility_status": "High" if volatility > 6 else "Normal" if volatility > 4 else "Low",
                    "suggested_position": get_position_suggestion(signal_result.signal.value, volatility)
                },
                "key_levels": {
                    "resistance": round(target_row['high'], 2),
                    "support": round(target_row['low'], 2),
                    "sma20": round(target_row['ema_20'], 2),
                    "sma50": round(target_row['sma_50'], 2),
                    "rsi_level": f"Oversold <30" if target_row['rsi'] < 30 else f"Overbought >70" if target_row['rsi'] > 70 else f"Neutral 30-70",
                    "current_rsi": round(target_row['rsi'], 1)
                },
                "trading_recommendations": get_trading_recommendations(signal_result.signal.value, target_row['close']),
                "market_context": get_market_context(df, target_idx, target_row),
                "historical_performance": get_historical_performance(df, engine, signal_result.metadata.get('regime', 'unknown')),
                "disclaimer": [
                    "This analysis is for educational purposes only",
                    "Past performance does not guarantee future results",
                    "Always do your own research before trading",
                    "Consider your risk tolerance and financial situation",
                    "Never risk more than you can afford to lose"
                ]
            }
            
            return SignalAnalysisResponse(
                success=True,
                data=response_data
            )
        
        else:
            return SignalAnalysisResponse(
                success=False,
                error="Insufficient data for analysis"
            )
        
    except Exception as e:
        return SignalAnalysisResponse(
            success=False,
            error=str(e)
        )
    finally:
        if 'conn' in locals():
            conn.close()

def get_regime_explanation(regime: str) -> Dict[str, Any]:
    """Get regime explanation"""
    explanations = {
        "mean_reversion": {
            "name": "Mean Reversion Regime",
            "description": "Market is showing signs of reverting to average",
            "focus": "Focus on oversold/overbought levels for reversals",
            "best_for": "Range-bound markets, pullback plays"
        },
        "trend_continuation": {
            "name": "Trend Continuation Regime",
            "description": "Market is in established uptrend",
            "focus": "Focus on pullbacks to trend lines",
            "best_for": "Momentum stocks, strong trends"
        },
        "breakout": {
            "name": "Breakout Regime",
            "description": "Market showing momentum expansion",
            "focus": "Focus on momentum continuation",
            "best_for": "Volatile breakouts, momentum plays"
        },
        "volatility_expansion": {
            "name": "Volatility Expansion Regime",
            "description": "High volatility detected - risk-off mode",
            "focus": "Focus on capital preservation",
            "best_for": "Risk management, defensive positions"
        }
    }
    return explanations.get(regime, {"name": "Unknown Regime", "description": "Regime not recognized"})

def get_risk_level(volatility: float) -> str:
    """Get risk level based on volatility"""
    if volatility > 6:
        return "HIGH"
    elif volatility > 4:
        return "MODERATE"
    else:
        return "LOW"

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

def get_trading_recommendations(signal: str, current_price: float) -> Dict[str, Any]:
    """Get trading recommendations"""
    if signal == "buy":
        return {
            "action": "Consider BUY position",
            "entry": f"${current_price:.2f}",
            "target": "+5-10% over 5-7 days",
            "stop_loss": "-3-5% from entry",
            "hold_time": "3-7 days"
        }
    elif signal == "sell":
        return {
            "action": "Consider SELL or SHORT",
            "entry": f"${current_price:.2f}",
            "target": "-5-10% over 3-5 days",
            "stop_loss": "+3% from entry",
            "hold_time": "2-5 days"
        }
    else:
        return {
            "action": "HOLD or WAIT",
            "entry": f"${current_price:.2f}",
            "target": "Wait for better entry point",
            "stop_loss": "Low risk",
            "hold_time": "Monitor daily"
        }

def get_market_context(df: pd.DataFrame, target_idx: int, target_row: pd.Series) -> Dict[str, Any]:
    """Get market context"""
    recent_5_days = df.iloc[max(0, target_idx-4):target_idx+1]
    recent_change_5d = (recent_5_days['close'].iloc[-1] / recent_5_days['close'].iloc[0] - 1) * 100
    recent_volatility = recent_5_days['close'].pct_change().std() * 100
    avg_volume = df['volume'].mean()
    volume_ratio = target_row['volume'] / avg_volume
    
    volume_status = "High volume detected - strong conviction" if volume_ratio > 1.5 else "Low volume detected - weak conviction" if volume_ratio < 0.5 else "Normal volume"
    
    return {
        "last_5_days": f"{recent_change_5d:+.1f}%",
        "recent_volatility": f"{recent_volatility:.1f}%",
        "volume_ratio": f"{volume_ratio:.1f}x average",
        "volume_status": volume_status
    }

def get_historical_performance(df: pd.DataFrame, engine: UnifiedTQQQSwingEngine, current_regime: str) -> Dict[str, Any]:
    """Get historical performance"""
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
                'signal': signal.signal.value,
                'return_5d': return_5d,
                'regime': signal.metadata.get('regime', 'unknown')
            })
            
        except Exception:
            continue
    
    hist_df = pd.DataFrame(historical_signals)
    
    if len(hist_df) > 0:
        buy_signals = hist_df[hist_df['signal'] == 'buy']
        result = {
            "buy_signals": {
                "total": len(buy_signals),
                "avg_return_5d": f"{buy_signals['return_5d'].mean():+.2%}" if len(buy_signals) > 0 else "N/A",
                "win_rate": f"{(buy_signals['return_5d'] > 0).mean() * 100:.1f}%" if len(buy_signals) > 0 else "N/A"
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
                    "avg_return_5d": f"{regime_buy_signals['return_5d'].mean():+.2%}",
                    "win_rate": f"{(regime_buy_signals['return_5d'] > 0).mean() * 100:.1f}%"
                }
        
        return result
    
    return {"message": "Insufficient historical data"}
