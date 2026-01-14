#!/usr/bin/env python3
"""
TQQQ Swing Engine API
Specialized API for TQQQ swing trading engine
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine

# Import TQQQ engine
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions
from app.utils.market_data_utils import calculate_market_regime_context
from app.observability.logging import get_logger, log_exception, log_with_context

router = APIRouter()

# Initialize logger for the API
logger = get_logger(__name__)

class TQQQSignalRequest(BaseModel):
    date: Optional[str] = None  # Format: YYYY-MM-DD

class TQQQSignalResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/signal/tqqq", response_model=TQQQSignalResponse)
async def generate_tqqq_signal(request: TQQQSignalRequest):
    """
    Generate signal using specialized TQQQ swing engine
    Optimized for TQQQ's 3x leveraged volatility characteristics
    """
    
    # Log request start
    logger.info(f"🚀 TQQQ signal request received", extra={
        'context': {
            'date': request.date,
            'endpoint': '/signal/tqqq',
            'request_id': id(request)
        }
    })
    
    try:
        # Load TQQQ data
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        # Use SQLAlchemy engine to avoid pandas warnings
        engine = create_engine(db_url)
        
        # Build query
        if request.date:
            query = """
                SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = 'TQQQ' AND i.date = %s
                ORDER BY i.date
            """
            params = (request.date,)
        else:
            # Get most recent data
            query = """
                SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = 'TQQQ'
                ORDER BY i.date DESC
                LIMIT 1
            """
            params = ()
        
        df = pd.read_sql(query, engine, params=params)
        
        logger.info(f"📊 Loaded {len(df)} rows of TQQQ data")
        
        if df.empty:
            logger.warning(f"⚠️ No TQQQ data found{' on ' + request.date if request.date else ''}")
            return TQQQSignalResponse(
                success=False,
                error=f"No TQQQ data found{' on ' + request.date if request.date else ''}"
            )
        
        df['date'] = pd.to_datetime(df['date'])
        row = df.iloc[0]
        
        # Calculate real market context
        target_date = request.date if request.date else str(row['date'].date())
        
        market_context = calculate_market_regime_context('TQQQ', target_date, settings.database_url)
        
        # Create market conditions with REAL data
        conditions = MarketConditions(
            rsi=row['rsi_14'],
            sma_20=row['ema_20'],
            sma_50=row['sma_50'],
            ema_20=row['ema_20'],
            current_price=row['close'],
            recent_change=market_context['recent_change'] / 100,  # Convert to decimal
            macd=row['macd'],
            macd_signal=row['macd_signal'],
            volatility=market_context['volatility'],  # Real volatility
            vix_level=market_context['vix_level'],  # VIX level for fear/greed
            volatility_trend='stable'  # Would need historical data to calculate trend
        )
        
        # Initialize TQQQ engine with specialized config
        #tqqq_config = SignalConfig(
        #    rsi_oversold=45,      # Higher threshold for TQQQ volatility
        #    rsi_moderately_oversold=35,
        #    rsi_mildly_oversold=50,
        #    max_volatility=8.0    # Higher volatility threshold for 3x leverage
        #)

        tqqq_config = SignalConfig(
    rsi_oversold=48,              # Shallow oversold (TQQQ recovers fast)
    rsi_moderately_oversold=38,   # True dip-buy zone
    rsi_mildly_oversold=43,       # Pullback zone
    max_volatility=8.0            # Appropriate for 3× ETF
)
        
        tqqq_engine = UnifiedTQQQSwingEngine(tqqq_config)
        tqqq_result = tqqq_engine.generate_signal(conditions)
        
        logger.info(f"✅ TQQQ signal generated successfully", extra={
            'context': {
                'signal': tqqq_result.signal.value,
                'confidence': tqqq_result.confidence,
                'regime': tqqq_result.metadata.get('regime'),
                'fear_greed_state': tqqq_result.metadata.get('fear_greed_state'),
                'recovery_detected': tqqq_result.metadata.get('recovery_detected')
            }
        })
        
        # Market data
        market_data = {
            'symbol': 'TQQQ',
            'date': str(row['date'].date()),
            'price': float(row['close']),
            'rsi': float(row['rsi_14']),
            'sma_20': float(row['ema_20']),
            'sma_50': float(row['sma_50']),
            'ema_20': float(row['ema_20']),
            'macd': float(row['macd']),
            'macd_signal': float(row['macd_signal']),
            'volume': int(row['volume']),
            'high': float(row['high']),
            'low': float(row['low'])
        }
        
        # TQQQ-specific analysis with REAL data
        price_change = (row['close'] - row['low']) / row['low'] * 100
        volatility_analysis = {
            'daily_range': f"{row['low']:.2f} - {row['high']:.2f}",
            'intraday_change': f"{price_change:.2f}%",
            'real_volatility': f"{market_context['volatility']:.2f}%",
            'recent_change': f"{market_context['recent_change']:.2f}%",
            'vix_level': f"{market_context['vix_level']:.2f}",
            'market_stress': market_context['market_stress'],
            'volatility_level': market_context['volatility_level']
        }
        
        return TQQQSignalResponse(
            success=True,
            data={
                'engine': {
                    'name': 'Unified TQQQ Swing Engine',
                    'type': 'specialized',
                    'description': 'Optimized for TQQQ 3x leveraged trading',
                    'config': {
                        'volatility_threshold': f"{tqqq_config.max_volatility}%",
                        'rsi_oversold': tqqq_config.rsi_oversold,
                        'risk_management': 'Aggressive volatility detection'
                    }
                },
                'market_data': market_data,
                'signal': {
                    'signal': tqqq_result.signal.value,
                    'confidence': tqqq_result.confidence,
                    'reasoning': tqqq_result.reasoning,
                    'metadata': tqqq_result.metadata
                },
                'analysis': volatility_analysis,
                'timestamp': datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error generating TQQQ signal: {str(e)}")
        log_exception(logger, e, "TQQQ signal generation API")
        
        return TQQQSignalResponse(
            success=False,
            data=None,
            error=f"Error generating TQQQ signal: {str(e)}"
        )

@router.get("/signal/tqqq/info")
async def get_tqqq_engine_info():
    """
    Get information about the TQQQ swing engine
    """
    
    return {
        'engine': {
            'name': 'Unified TQQQ Swing Engine',
            'type': 'specialized',
            'description': 'Specialized swing trading engine for TQQQ (3x leveraged NASDAQ-100 ETF)',
            'characteristics': [
                'High volatility tolerance',
                'Aggressive risk management',
                '3x leverage awareness',
                'Optimized for intraday swings'
            ],
            'regimes': [
                'MEAN_REVERSION',
                'TREND_CONTINUATION', 
                'BREAKOUT',
                'VOLATILITY_EXPANSION'
            ],
            'config': {
                'volatility_threshold': '8.0%',
                'rsi_oversold': 45,
                'rsi_overbought': 70,
                'risk_off_downtrend': True
            },
            'features': [
                'Market regime detection',
                'Volatility expansion detection',
                'Mean reversion logic',
                'Trend continuation',
                'Breakout momentum',
                'Risk-off mode for downtrends'
            ]
        },
        'usage': {
            'endpoint': '/signal/tqqq',
            'method': 'POST',
            'description': 'Generate TQQQ swing trading signal',
            'parameters': {
                'date': 'YYYY-MM-DD (optional, defaults to most recent)'
            }
        }
    }
