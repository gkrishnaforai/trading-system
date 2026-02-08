"""
Audit API Endpoints for Streamlit Admin Dashboard
Provides real-time audit data for FMP API integration and data loading monitoring
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, date
from pydantic import BaseModel
import logging

from app.database import db

# Initialize router
audit_router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
logger = logging.getLogger(__name__)

class FmpApiStatusResponse(BaseModel):
    """Response model for FMP API status"""
    fmp_api_dominant: bool
    fmp_percentage: float
    total_records: int
    fmp_records: int
    calculated_records: int
    error: Optional[str] = None

class SymbolDataAvailability(BaseModel):
    """Model for symbol data availability"""
    symbol: str
    data_completeness: int
    uses_fmp_api: bool
    missing_data_types: List[str]
    last_updated: str

class AuditRecord(BaseModel):
    """Model for audit record"""
    timestamp: str
    level: str
    symbol: str
    operation: str
    provider: Optional[str] = None
    duration_ms: int
    records_in: int
    records_saved: int
    message: Optional[str] = None
    data_source: Optional[str] = None


def _table_exists(table_name: str) -> bool:
    try:
        result = db.execute_query_positional(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = $1
            LIMIT 1
            """,
            [table_name],
        )
        return bool(result)
    except Exception:
        return False

@audit_router.get("/provider-distribution/{audit_date}")
async def get_provider_distribution_status(audit_date: date):
    """Get universal provider distribution status for all data sources"""
    try:
        # Query all data sources for the selected date
        provider_data = {}
        total_records = 0
        total_symbols = set()
        warnings: List[str] = []
        
        # Get indicators data source distribution
        indicators_query = """
            SELECT 
                data_source,
                COUNT(*) as record_count,
                COUNT(DISTINCT symbol) as symbol_count
            FROM indicators_daily 
            WHERE date::date = $1
            GROUP BY data_source
            ORDER BY record_count DESC
        """
        
        try:
            indicators_results = db.execute_query_positional(indicators_query, [audit_date])
        except Exception as e:
            indicators_results = []
            warnings.append(f"indicators_daily unavailable: {str(e)}")
        
        for row in indicators_results:
            provider = row['data_source']
            provider_data[provider] = {
                'record_count': row['record_count'],
                'symbol_count': row['symbol_count'],
                'data_types': ['indicators']
            }
            total_records += row['record_count']
            total_symbols.update([f"indicator_{row['symbol_count']}"])
        
        # Get price data source distribution
        if not _table_exists("price_historical_daily"):
            warnings.append("price_historical_daily unavailable: table does not exist")
            price_results = []
        else:
            price_query = """
                SELECT 
                    'yahoo_finance' as data_source,
                    COUNT(*) as record_count,
                    COUNT(DISTINCT symbol) as symbol_count
                FROM price_historical_daily 
                WHERE date::date = $1
            """
            
            try:
                price_results = db.execute_query_positional(price_query, [audit_date])
            except Exception as e:
                price_results = []
                warnings.append(f"price_historical_daily unavailable: {str(e)}")
        
        for row in price_results:
            provider = row['data_source']
            if provider in provider_data:
                provider_data[provider]['record_count'] += row['record_count']
                provider_data[provider]['symbol_count'] += row['symbol_count']
                provider_data[provider]['data_types'].append('price_historical')
            else:
                provider_data[provider] = {
                    'record_count': row['record_count'],
                    'symbol_count': row['symbol_count'],
                    'data_types': ['price_historical']
                }
            total_records += row['record_count']
            total_symbols.update([f"price_{row['symbol_count']}"])
        
        # Determine primary provider (most records)
        primary_provider = max(provider_data.keys(), key=lambda x: provider_data[x]['record_count']) if provider_data else "Unknown"
        
        return {
            "total_records": total_records,
            "primary_provider": primary_provider,
            "symbols_processed": len(total_symbols),
            "providers": provider_data,
            "audit_date": str(audit_date),
            "warnings": warnings,
        }
        
    except Exception as e:
        logger.error(f"Error getting provider distribution for {audit_date}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@audit_router.get("/fmp-status/{audit_date}", response_model=FmpApiStatusResponse)
async def get_fmp_api_status(audit_date: date):
    """Get FMP API integration status for a specific date"""
    try:
        # Query indicators_daily table for data source distribution
        query = """
            SELECT 
                data_source,
                COUNT(*) as record_count,
                COUNT(DISTINCT symbol) as symbol_count
            FROM indicators_daily 
            WHERE date::date = $1
            GROUP BY data_source
            ORDER BY record_count DESC
        """
        
        results = db.execute_query_positional(query, [audit_date])
        
        total_records = sum(row['record_count'] for row in results)
        fmp_records = 0
        calculated_records = 0
        
        for row in results:
            if row['data_source'] == 'fmp_api':
                fmp_records = row['record_count']
            elif row['data_source'] == 'calculated':
                calculated_records = row['record_count']
        
        fmp_percentage = (fmp_records / max(total_records, 1)) * 100
        fmp_dominant = fmp_percentage > 80  # Consider FMP dominant if >80%
        
        return FmpApiStatusResponse(
            fmp_api_dominant=fmp_dominant,
            fmp_percentage=fmp_percentage,
            total_records=total_records,
            fmp_records=fmp_records,
            calculated_records=calculated_records
        )
        
    except Exception as e:
        logger.error(f"Error getting FMP API status for {audit_date}: {e}")
        return FmpApiStatusResponse(
            fmp_api_dominant=False,
            fmp_percentage=0.0,
            total_records=0,
            fmp_records=0,
            calculated_records=0,
            error=str(e)
        )

@audit_router.get("/fmp-audit-data/{audit_date}")
async def get_fmp_audit_data(audit_date: date):
    """Get comprehensive FMP API audit data for a specific date"""
    try:
        # Get detailed breakdown by data type
        query = """
            SELECT 
                'indicators' as data_type,
                data_source,
                COUNT(*) as record_count,
                COUNT(DISTINCT symbol) as symbol_count
            FROM indicators_daily 
            WHERE date::date = $1
            GROUP BY data_source
        """
        
        results = db.execute_query_positional(query, [audit_date])
        
        # Get price data info
        if _table_exists("price_historical_daily"):
            price_query = """
                SELECT 
                    COUNT(*) as record_count,
                    COUNT(DISTINCT symbol) as symbol_count
                FROM price_historical_daily 
                WHERE date::date = %s
            """
            
            price_query = price_query.replace("%s", "$1")
            price_results = db.execute_query_positional(price_query, [audit_date])
            price_count = price_results[0]['record_count'] if price_results else 0
            price_symbols = price_results[0]['symbol_count'] if price_results else 0
        else:
            price_count = 0
            price_symbols = 0
        
        # Process indicators data
        fmp_indicators = 0
        calculated_indicators = 0
        total_symbols = set()
        
        for row in results:
            if row['data_source'] == 'fmp_api':
                fmp_indicators = row['record_count']
                total_symbols.update([f"indicators_{row['symbol_count']}"])
            elif row['data_source'] == 'calculated':
                calculated_indicators = row['record_count']
        
        total_symbols_count = len(total_symbols) + price_symbols
        
        return {
            "fmp_api_records": fmp_indicators,
            "calculated_records": calculated_indicators,
            "total_records": fmp_indicators + calculated_indicators,
            "symbols_processed": total_symbols_count,
            "data_types": {
                "price_historical": {"fmp": price_count, "calculated": 0},
                "indicators": {"fmp": fmp_indicators, "calculated": calculated_indicators}
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting FMP audit data for {audit_date}: {e}")
        return {"error": str(e)}

@audit_router.get("/symbol-availability/{audit_date}", response_model=List[SymbolDataAvailability])
async def get_symbol_data_availability(audit_date: date):
    """Get data availability status for all symbols on a specific date"""
    try:
        # Get all symbols that have data on the selected date
        symbols_query = """
            SELECT DISTINCT symbol 
            FROM indicators_daily 
            WHERE date::date = $1
            ORDER BY symbol
            LIMIT 20
        """
        
        symbols_result = db.execute_query_positional(symbols_query, [audit_date])
        
        symbol_data = []
        
        for symbol_row in symbols_result:
            symbol = symbol_row['symbol']
            
            # Check data completeness for this symbol
            completeness_query = """
                SELECT 
                    data_source,
                    COUNT(DISTINCT indicator_name) as indicator_count,
                    COUNT(*) as total_records,
                    MAX(created_at) as last_updated
                FROM indicators_daily 
                WHERE symbol = $1 AND date::date = $2
                GROUP BY data_source
            """
            
            completeness_result = db.execute_query_positional(completeness_query, [symbol, audit_date])
            
            # Calculate completeness and data source usage
            total_indicators = sum(row['indicator_count'] for row in completeness_result)
            primary_indicators = 0
            primary_provider = 'Unknown'
            uses_primary_provider = False
            
            # Determine primary provider (most indicators)
            if completeness_result:
                primary_row = max(completeness_result, key=lambda x: x['indicator_count'])
                primary_provider = primary_row['data_source']
                primary_indicators = primary_row['indicator_count']
                uses_primary_provider = primary_indicators > 0
            
            # Expected indicators (list of standard technical indicators)
            expected_indicators = ['ema_20', 'ema_50', 'sma_20', 'sma_50', 'sma_200', 'rsi_14', 'macd', 'bollinger_bands']
            missing_indicators = [ind for ind in expected_indicators if ind not in [row['indicator_name'] for row in completeness_result]]
            
            # Calculate completeness percentage
            completeness = min(100, (total_indicators / len(expected_indicators)) * 100) if expected_indicators else 0
            
            # Get last updated timestamp
            last_updated = max((row['last_updated'] for row in completeness_result), default=datetime.now())
            
            symbol_data.append(SymbolDataAvailability(
                symbol=symbol,
                data_completeness=int(completeness),
                uses_fmp_api=primary_provider == 'fmp_api',  # Keep for backward compatibility
                missing_data_types=missing_indicators,
                last_updated=last_updated.strftime('%Y-%m-%d %H:%M:%S')
            ))
            
            # Add provider-specific data
            symbol_data[-1]['primary_provider'] = primary_provider
            symbol_data[-1]['uses_primary_provider'] = uses_primary_provider
        
        return symbol_data
        
    except Exception as e:
        logger.error(f"Error getting symbol availability for {audit_date}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@audit_router.get("/audit-records/{audit_date}", response_model=List[AuditRecord])
async def get_audit_records(
    audit_date: date,
    show_only_errors: bool = Query(False),
    show_only_primary: bool = Query(False),
    limit: int = Query(100, le=500)
):
    """Get detailed audit records for a specific date with filters"""
    try:
        # Build base query
        base_query = """
            SELECT 
                event_ts as timestamp,
                level,
                symbol,
                operation,
                provider,
                duration_ms,
                records_in,
                records_saved,
                message,
                context
            FROM data_ingestion_events 
            WHERE DATE(event_ts) = $1
        """
        
        params = [audit_date]
        
        # Add filters
        if show_only_errors:
            base_query += " AND level = 'error'"
        
        if show_only_primary:
            base_query += " AND (provider = 'fmp' OR context->>'data_source' = 'fmp_api')"
        
        base_query += " ORDER BY event_ts DESC LIMIT $2"
        params.append(limit)
        
        results = db.execute_query_positional(base_query, params)
        
        audit_records = []
        for row in results:
            # Extract data source from context or operation
            context = row['context'] or {}
            data_source = context.get('data_source', 'unknown')
            
            # If context doesn't have data_source, try to infer from provider
            if data_source == 'unknown':
                if row['provider'] == 'fmp':
                    data_source = 'fmp_api'
                elif row['provider'] == 'yahoo_finance':
                    data_source = 'yahoo_finance'
                else:
                    data_source = row['provider']
            
            audit_records.append(AuditRecord(
                timestamp=row['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                level=row['level'],
                symbol=row['symbol'] or 'system',
                operation=row['operation'],
                provider=row['provider'] or 'unknown',
                duration_ms=row['duration_ms'] or 0,
                records_in=row['records_in'] or 0,
                records_saved=row['records_saved'] or 0,
                message=row['message'] or "",
                data_source=(data_source or 'unknown')
            ))
        
        return audit_records
        
    except Exception as e:
        logger.error(f"Error getting audit records for {audit_date}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@audit_router.post("/reload-symbol/{symbol}")
async def reload_symbol_data(symbol: str):
    """Trigger data reload for a specific symbol"""
    try:
        # Import here to avoid circular imports
        from app.data_management.refresh_manager import DataRefreshManager
        from app.data_management.refresh_strategy import DataType, RefreshMode
        
        # Initialize refresh manager
        manager = DataRefreshManager()
        
        # Trigger reload for key data types
        result = manager.refresh_data(
            symbol=symbol.upper(),
            data_types=[DataType.PRICE_HISTORICAL, DataType.INDICATORS],
            mode=RefreshMode.ON_DEMAND,
            force=True
        )
        
        return {
            "success": result.total_failed == 0,
            "message": f"Reload initiated for {symbol}",
            "total_successful": result.total_successful,
            "total_failed": result.total_failed,
            "results": {
                data_type: {
                    "status": result.status.value,
                    "message": result.message,
                    "rows_affected": result.rows_affected
                }
                for data_type, result in result.results.items()
            }
        }
        
    except Exception as e:
        logger.error(f"Error reloading data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@audit_router.get("/system-overview/{audit_date}")
async def get_system_overview(audit_date: date):
    """Get comprehensive system overview for a specific date"""
    try:
        # Get table statistics
        tables_query = """
            SELECT 
                table_name,
                (
                    SELECT COUNT(*) 
                    FROM information_schema.columns 
                    WHERE table_name = t.table_name
                ) as column_count
            FROM information_schema.tables t
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        
        tables_result = db.execute_query(tables_query)
        
        # Get record counts for key tables
        key_tables = [
            'indicators_daily', 'price_historical_daily', 'data_ingestion_events',
            'stocks', 'fundamentals_snapshots', 'earnings_data'
        ]
        
        table_stats = {}
        for table in key_tables:
            try:
                count_query = f"SELECT COUNT(*) as record_count FROM {table}"
                count_result = db.execute_query(count_query)
                table_stats[table] = count_result[0]['record_count']
            except:
                table_stats[table] = 0
        
        # Get data ingestion stats for the date
        ingestion_query = """
            SELECT 
                level,
                COUNT(*) as count,
                AVG(duration_ms) as avg_duration
            FROM data_ingestion_events 
            WHERE DATE(event_ts) = $1
            GROUP BY level
        """
        
        ingestion_result = db.execute_query_positional(ingestion_query, [audit_date])
        
        return {
            "total_tables": len(tables_result),
            "table_details": [
                {"name": row['table_name'], "columns": row['column_count']}
                for row in tables_result
            ],
            "key_table_records": table_stats,
            "ingestion_stats": [
                {
                    "level": row['level'],
                    "count": row['count'],
                    "avg_duration": round(row['avg_duration'], 2) if row['avg_duration'] else 0
                }
                for row in ingestion_result
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting system overview for {audit_date}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
