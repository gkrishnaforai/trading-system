#!/usr/bin/env python3
"""
Simple API for TQQQ Unified Swing Engine
Generate signals for specific dates using the unified engine
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

class SignalRequest(BaseModel):
    symbol: str = "TQQQ"
    date: Optional[str] = None  # Format: YYYY-MM-DD

class SignalResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/signal/unified-tqqq", response_model=SignalResponse)
async def generate_unified_tqqq_signal(request: SignalRequest):
    """
    Generate signal using unified TQQQ swing engine for specific date
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
            date_filter = "ORDER BY i.date DESC LIMIT 1"
        
        cursor.execute(f"""
            SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
            FROM indicators_daily i
            JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
            WHERE i.symbol = '{request.symbol}' 
            {date_filter}
        """)
        
        rows = cursor.fetchall()
        
        if not rows:
            return SignalResponse(
                success=False,
                error=f"No data found for {request.symbol} on {request.date or 'latest date'}"
            )
        
        # Get the target row
        target_row = rows[0]
        
        # Get historical data for volatility calculation
        if request.date:
            target_date = pd.to_datetime(request.date)
            cursor.execute(f"""
                SELECT i.date, r.close
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = '{request.symbol}' 
                AND i.date >= '{target_date - timedelta(days=19)}'
                AND i.date <= '{target_date}'
                ORDER BY i.date
            """)
        else:
            # For latest, get last 20 days
            cursor.execute(f"""
                SELECT i.date, r.close
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = '{request.symbol}' 
                ORDER BY i.date DESC
                LIMIT 20
            """)
        
        historical_rows = cursor.fetchall()
        
        if len(historical_rows) < 10:
            return SignalResponse(
                success=False,
                error="Insufficient historical data for analysis"
            )
        
        # Calculate volatility
        hist_df = pd.DataFrame(historical_rows, columns=['date', 'close'])
        hist_df['date'] = pd.to_datetime(hist_df['date'])
        hist_df = hist_df.sort_values('date')
        
        volatility_data = hist_df['close'].pct_change().dropna()
        volatility = volatility_data.std() * 100 if len(volatility_data) > 1 else 2.0
        
        # Calculate recent change
        if len(historical_rows) >= 3:
            recent_close = historical_rows[-3][1]  # 3 days ago
            current_close = target_row[1]
            recent_change = (current_close - recent_close) / recent_close
        else:
            recent_change = 0.0
        
        # Initialize unified engine
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        # Create market conditions
        conditions = MarketConditions(
            rsi=target_row[2],  # rsi_14
            sma_20=target_row[4],  # ema_20
            sma_50=target_row[3],  # sma_50
            ema_20=target_row[4],  # ema_20
            current_price=target_row[1],  # close
            recent_change=recent_change,
            macd=target_row[5],  # macd
            macd_signal=target_row[6],  # macd_signal
            volatility=volatility
        )
        
        # Generate signal
        signal_result = engine.generate_signal(conditions)
        
        # Build response
        response_data = {
            "symbol": request.symbol,
            "date": target_row[0].strftime('%Y-%m-%d'),
            "signal": signal_result.signal.value.upper(),
            "confidence": round(signal_result.confidence, 2),
            "confidence_percent": int(signal_result.confidence * 100),
            "regime": signal_result.metadata.get('regime', 'unknown').replace('_', ' ').title(),
            "reasoning": signal_result.reasoning,
            "market_data": {
                "price": round(target_row[1], 2),
                "rsi": round(target_row[2], 1),
                "sma20": round(target_row[4], 2),
                "sma50": round(target_row[3], 2),
                "volume": int(target_row[7]),
                "high": round(target_row[8], 2),
                "low": round(target_row[9], 2),
                "recent_change": round(recent_change * 100, 2),
                "volatility": round(volatility, 1)
            },
            "technical_analysis": {
                "rsi_status": "OVERSOLD" if target_row[2] < 35 else "OVERBOUGHT" if target_row[2] > 70 else "NEUTRAL",
                "trend": "UPTREND" if target_row[4] > target_row[3] else "DOWNTREND" if target_row[4] < target_row[3] else "SIDEWAYS",
                "price_vs_sma20": "ABOVE" if target_row[1] > target_row[4] else "BELOW",
                "price_vs_sma50": "ABOVE" if target_row[1] > target_row[3] else "BELOW"
            },
            "engine_info": {
                "name": "Unified TQQQ Swing Engine",
                "version": "1.0.0",
                "description": "Regime-aware signal engine with market classification",
                "features": [
                    "Market regime classification",
                    "Regime-specific signal logic", 
                    "Always generates BUY/SELL/HOLD",
                    "Optimized for TQQQ characteristics",
                    "Comprehensive reasoning provided"
                ]
            }
        }
        
        conn.close()
        
        return SignalResponse(
            success=True,
            data=response_data
        )
        
    except Exception as e:
        return SignalResponse(
            success=False,
            error=str(e)
        )
    finally:
        if 'conn' in locals():
            conn.close()

@router.get("/signal/unified-tqqq/health")
async def health_check():
    """Health check for unified TQQQ engine"""
    try:
        # Test engine initialization
        config = SignalConfig(
            rsi_oversold=45,
            rsi_moderately_oversold=35,
            rsi_mildly_oversold=50,
            max_volatility=8.0
        )
        
        engine = UnifiedTQQQSwingEngine(config)
        
        return {
            "status": "healthy",
            "engine": "Unified TQQQ Swing Engine",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "features": [
                "Market regime classification",
                "Regime-specific signal logic",
                "Always generates BUY/SELL/HOLD",
                "Optimized for TQQQ characteristics"
            ]
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
