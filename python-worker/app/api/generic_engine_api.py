#!/usr/bin/env python3
"""
Generic Swing Engine API
Adaptable API for various ETFs and stocks using generic swing engine
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

# Import generic engine
from app.signal_engines.generic_etf_engine import create_instrument_engine
from app.signal_engines.signal_calculator_core import MarketConditions
from app.utils.market_data_utils import calculate_market_regime_context

router = APIRouter()

class GenericSignalRequest(BaseModel):
    symbol: str
    date: Optional[str] = None  # Format: YYYY-MM-DD

class GenericSignalResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class MultiGenericSignalRequest(BaseModel):
    symbols: List[str]
    date: Optional[str] = None  # Format: YYYY-MM-DD

class MultiGenericSignalResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/signal/generic", response_model=GenericSignalResponse)
async def generate_generic_signal(request: GenericSignalRequest):
    """
    Generate signal using generic swing engine for any symbol
    Automatically adapts to symbol type (ETF vs Stock) and sector
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
            return GenericSignalResponse(
                success=False,
                error=f"No data found for {request.symbol}{' on ' + request.date if request.date else ''}"
            )
        
        df['date'] = pd.to_datetime(df['date'])
        row = df.iloc[0]
        
        # Calculate real market context
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/trading_db')
        target_date = request.date if request.date else str(row['date'].date())
        
        market_context = calculate_market_regime_context(request.symbol.upper(), target_date, db_url)
        
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
            volatility=market_context['volatility']  # Real volatility
        )
        
        # Create generic engine for symbol
        generic_engine = create_instrument_engine(request.symbol.upper())
        generic_result = generic_engine.generate_signal(conditions)
        
        # Get engine metadata
        try:
            engine_metadata = generic_engine.get_engine_metadata()
        except:
            engine_metadata = {
                'display_name': f'{request.symbol.upper()} Swing Engine',
                'description': 'Generic swing engine'
            }
        
        # Market data
        market_data = {
            'symbol': request.symbol.upper(),
            'date': str(row['date'].date()),
            'price': float(row['close']),
            'rsi': float(row['rsi_14']),
            'sma_20': float(row['ema_20']),
            'sma_50': float(row['sma_50']),
            'volume': int(row['volume']),
            'high': float(row['high']),
            'low': float(row['low'])
        }
        
        # Symbol-specific analysis with REAL data
        symbol_type = engine_metadata.get('instrument_type', 'UNKNOWN')
        price_change = (row['close'] - row['low']) / row['low'] * 100
        
        symbol_analysis = {
            'symbol_type': symbol_type,
            'daily_range': f"{row['low']:.2f} - {row['high']:.2f}",
            'intraday_change': f"{price_change:.2f}%",
            'real_volatility': f"{market_context['volatility']:.2f}%",
            'recent_change': f"{market_context['recent_change']:.2f}%",
            'vix_level': f"{market_context['vix_level']:.2f}",
            'market_stress': market_context['market_stress'],
            'volatility_level': market_context['volatility_level'],
            'engine_config': engine_metadata.get('config', {})
        }
        
        return GenericSignalResponse(
            success=True,
            data={
                'engine': {
                    'name': engine_metadata.get('display_name', f'{request.symbol.upper()} Swing Engine'),
                    'type': 'generic',
                    'description': engine_metadata.get('description', 'Adaptable swing trading engine'),
                    'instrument_type': symbol_type,
                    'config': engine_metadata.get('config', {})
                },
                'market_data': market_data,
                'signal': {
                    'signal': generic_result.signal.value,
                    'confidence': generic_result.confidence,
                    'reasoning': generic_result.reasoning,
                    'metadata': generic_result.metadata
                },
                'analysis': symbol_analysis,
                'timestamp': datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        return GenericSignalResponse(
            success=False,
            error=f"Error generating generic signal for {request.symbol}: {str(e)}"
        )

@router.post("/signal/generic/multi", response_model=MultiGenericSignalResponse)
async def generate_multi_generic_signals(request: MultiGenericSignalRequest):
    """
    Generate signals for multiple symbols using generic swing engine
    """
    
    try:
        all_results = {}
        
        for symbol in request.symbols:
            # Create individual request
            individual_request = GenericSignalRequest(symbol=symbol, date=request.date)
            result = await generate_generic_signal(individual_request)
            
            if result.success:
                all_results[symbol] = result.data
            else:
                all_results[symbol] = {'error': result.error}
        
        # Summary
        successful_symbols = [s for s, r in all_results.items() if 'error' not in r]
        failed_symbols = [s for s, r in all_results.items() if 'error' in r]
        
        # Signal summary
        signal_summary = {}
        for symbol, result in all_results.items():
            if 'signal' in result:
                signal = result['signal']['signal']
                if signal not in signal_summary:
                    signal_summary[signal] = 0
                signal_summary[signal] += 1
        
        return MultiGenericSignalResponse(
            success=len(successful_symbols) > 0,
            data={
                'symbols': all_results,
                'summary': {
                    'total_symbols': len(request.symbols),
                    'successful': len(successful_symbols),
                    'failed': len(failed_symbols),
                    'successful_symbols': successful_symbols,
                    'failed_symbols': failed_symbols,
                    'signal_distribution': signal_summary
                }
            }
        )
        
    except Exception as e:
        return MultiGenericSignalResponse(
            success=False,
            error=f"Error generating multi generic signals: {str(e)}"
        )

@router.get("/signal/generic/engines")
async def get_available_generic_engines():
    """
    Get information about available generic engine types
    """
    
    try:
        from app.signal_engines.generic_etf_engine import get_available_instrument_types
        
        instrument_types = get_available_instrument_types()
        
        return {
            'engine': {
                'name': 'Generic Swing Engine',
                'type': 'adaptable',
                'description': 'Adaptable swing trading engine for various ETFs and stocks',
                'characteristics': [
                    'Symbol-specific configuration',
                    'Automatic type detection',
                    'Sector-specific tuning',
                    'Market cap awareness'
                ],
                'supported_types': instrument_types,
                'features': [
                    'Market regime classification',
                    'Regime-specific signal logic',
                    'Always generates BUY/SELL/HOLD',
                    'Optimized for each instrument type',
                    'Uses proven TQQQ engine logic'
                ]
            },
            'usage': {
                'single_endpoint': '/signal/generic',
                'multi_endpoint': '/signal/generic/multi',
                'method': 'POST',
                'description': 'Generate swing trading signals for any symbol'
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting generic engine info: {str(e)}")

@router.get("/signal/generic/symbols")
async def get_available_generic_symbols():
    """
    Get symbols available for generic swing engine testing
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
                'days_available': (row['end_date'] - row['start_date']).days + 1 if row['start_date'] and row['end_date'] else 0,
                'suitable_for_swing': row['record_count'] >= 50  # Minimum for swing analysis
            })
        
        return {
            'symbols': symbols,
            'total_symbols': len(symbols),
            'suitable_for_swing': len([s for s in symbols if s['suitable_for_swing']]),
            'message': f'Found {len(symbols)} symbols with indicator data'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting symbols: {str(e)}")
