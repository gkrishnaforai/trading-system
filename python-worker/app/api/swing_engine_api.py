#!/usr/bin/env python3
"""
Swing Trading Engine API
Generate signals for multiple symbols using swing engines
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import pandas as pd
from datetime import datetime

# Import engines
from app.signal_engines.unified_tqqq_swing_engine import UnifiedTQQQSwingEngine
from app.signal_engines.generic_etf_engine import create_instrument_engine
from app.signal_engines.signal_calculator_core import SignalConfig, MarketConditions

router = APIRouter()

class SignalRequest(BaseModel):
    symbol: str
    date: Optional[str] = None  # Format: YYYY-MM-DD

class SignalResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class MultiSignalRequest(BaseModel):
    symbols: List[str]
    date: Optional[str] = None  # Format: YYYY-MM-DD

class MultiSignalResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/signal/swing", response_model=SignalResponse)
async def generate_swing_signal(request: SignalRequest):
    """
    Generate signal using swing engine for specific symbol and date
    """
    
    try:
        # Load data
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        conn = psycopg2.connect(db_url)
        
        # Build query
        if request.date:
            query = """
                SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = %s AND i.date = %s
                ORDER BY i.date
            """
            params = (request.symbol.upper(), request.date)
        else:
            # Get most recent data
            query = """
                SELECT i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, r.volume, r.low, r.high
                FROM indicators_daily i
                JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
                WHERE i.symbol = %s
                ORDER BY i.date DESC
                LIMIT 1
            """
            params = (request.symbol.upper(),)
        
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        if df.empty:
            return SignalResponse(
                success=False,
                error=f"No data found for {request.symbol}{' on ' + request.date if request.date else ''}"
            )
        
        df['date'] = pd.to_datetime(df['date'])
        row = df.iloc[0]
        
        # Create market conditions
        conditions = MarketConditions(
            rsi=row['rsi_14'],
            sma_20=row['ema_20'],
            sma_50=row['sma_50'],
            ema_20=row['ema_20'],
            current_price=row['close'],
            recent_change=0.0,  # Simplified for API
            macd=row['macd'],
            macd_signal=row['macd_signal'],
            volatility=2.0  # Default
        )
        
        # Generate signals
        results = {}
        
        # TQQQ engine (for TQQQ symbol)
        if request.symbol.upper() == 'TQQQ':
            try:
                tqqq_config = SignalConfig(
                    rsi_oversold=45,
                    rsi_moderately_oversold=35,
                    rsi_mildly_oversold=50,
                    max_volatility=8.0
                )
                tqqq_engine = UnifiedTQQQSwingEngine(tqqq_config)
                tqqq_result = tqqq_engine.generate_signal(conditions)
                
                results['tqqq_engine'] = {
                    'signal': tqqq_result.signal.value,
                    'confidence': tqqq_result.confidence,
                    'reasoning': tqqq_result.reasoning[:3],  # First 3 reasons
                    'metadata': tqqq_result.metadata
                }
            except Exception as e:
                results['tqqq_engine'] = {'error': str(e)}
        
        # Generic engine
        try:
            generic_engine = create_instrument_engine(request.symbol.upper())
            generic_result = generic_engine.generate_signal(conditions)
            
            results['generic_engine'] = {
                'signal': generic_result.signal.value,
                'confidence': generic_result.confidence,
                'reasoning': generic_result.reasoning[:3],  # First 3 reasons
                'metadata': generic_result.metadata
            }
        except Exception as e:
            results['generic_engine'] = {'error': str(e)}
        
        # Market data
        market_data = {
            'symbol': request.symbol.upper(),
            'date': str(row['date'].date()),
            'price': float(row['close']),
            'rsi': float(row['rsi_14']),
            'sma_20': float(row['ema_20']),
            'sma_50': float(row['sma_50']),
            'volume': int(row['volume'])
        }
        
        return SignalResponse(
            success=True,
            data={
                'market_data': market_data,
                'signals': results,
                'agreement': results.get('tqqq_engine', {}).get('signal') == results.get('generic_engine', {}).get('signal') if 'tqqq_engine' in results and 'generic_engine' in results else None
            }
        )
        
    except Exception as e:
        return SignalResponse(
            success=False,
            error=f"Error generating signal: {str(e)}"
        )

@router.post("/signal/swing/multi", response_model=MultiSignalResponse)
async def generate_multi_swing_signals(request: MultiSignalRequest):
    """
    Generate signals for multiple symbols using swing engines
    """
    
    try:
        all_results = {}
        
        for symbol in request.symbols:
            # Create individual request
            individual_request = SignalRequest(symbol=symbol, date=request.date)
            result = await generate_swing_signal(individual_request)
            all_results[symbol] = result.data if result.success else {'error': result.error}
        
        # Summary
        successful_symbols = [s for s, r in all_results.items() if r.get('success', True)]
        failed_symbols = [s for s, r in all_results.items() if not r.get('success', True)]
        
        return MultiSignalResponse(
            success=len(successful_symbols) > 0,
            data={
                'symbols': all_results,
                'summary': {
                    'total_symbols': len(request.symbols),
                    'successful': len(successful_symbols),
                    'failed': len(failed_symbols),
                    'successful_symbols': successful_symbols,
                    'failed_symbols': failed_symbols
                }
            }
        )
        
    except Exception as e:
        return MultiSignalResponse(
            success=False,
            error=f"Error generating multi signals: {str(e)}"
        )

@router.get("/signal/swing/engines")
async def get_available_engines():
    """
    Get information about available swing engines
    """
    
    try:
        from app.signal_engines.generic_etf_engine import get_available_instrument_types
        
        engines = {
            'tqqq_engine': {
                'name': 'Unified TQQQ Swing Engine',
                'description': 'Specialized engine for TQQQ with aggressive volatility detection',
                'supported_symbols': ['TQQQ'],
                'features': ['Market regime detection', 'Volatility expansion', 'Mean reversion', 'Trend continuation', 'Breakout']
            },
            'generic_engine': {
                'name': 'Generic Instrument Swing Engine',
                'description': 'Configurable engine for various ETFs and stocks',
                'supported_symbols': 'All symbols with data',
                'features': ['Symbol-specific configuration', 'Market regime classification', 'Regime-specific logic']
            }
        }
        
        # Get available instrument types
        try:
            instrument_types = get_available_instrument_types()
            engines['generic_engine']['available_types'] = instrument_types
        except:
            engines['generic_engine']['available_types'] = []
        
        return {
            'engines': engines,
            'status': 'active'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting engine info: {str(e)}")

@router.get("/signal/swing/symbols")
async def get_available_symbols():
    """
    Get list of symbols with available data for swing engine testing
    """
    
    try:
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        
        conn = psycopg2.connect(db_url)
        
        query = """
            SELECT DISTINCT symbol, 
                   COUNT(*) as record_count,
                   MIN(date) as start_date,
                   MAX(date) as end_date
            FROM indicators_daily 
            GROUP BY symbol 
            ORDER BY symbol
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        if df.empty:
            return {'symbols': [], 'message': 'No symbols with indicator data found'}
        
        symbols = []
        for _, row in df.iterrows():
            symbols.append({
                'symbol': row['symbol'],
                'record_count': int(row['record_count']),
                'date_range': f"{row['start_date']} to {row['end_date']}",
                'days_available': (row['end_date'] - row['start_date']).days + 1 if row['start_date'] and row['end_date'] else 0
            })
        
        return {
            'symbols': symbols,
            'total_symbols': len(symbols),
            'message': f'Found {len(symbols)} symbols with indicator data'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting symbols: {str(e)}")
