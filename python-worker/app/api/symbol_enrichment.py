"""
API endpoints for symbol enrichment and missing symbols management.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from pydantic import BaseModel
import logging

from app.services.symbol_enrichment_service import SymbolEnrichmentService

logger = logging.getLogger(__name__)

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/symbols", tags=["symbols"])
# CORRECT: router = APIRouter(tags=["symbols"])
# ========================================
router = APIRouter(tags=["symbols"])

class EnrichSymbolsRequest(BaseModel):
    batch_size: int = 10

class EnrichSymbolsResponse(BaseModel):
    processed: int
    completed: int
    failed: int
    skipped: int

@router.post("/enrich-missing", response_model=EnrichSymbolsResponse)
async def enrich_missing_symbols(
    request: EnrichSymbolsRequest,
    background_tasks: BackgroundTasks
) -> EnrichSymbolsResponse:
    """
    Process missing symbols from the queue and enrich them with stock data.
    
    This endpoint:
    1. Gets pending symbols from the missing_symbols_queue table
    2. Fetches comprehensive stock data from Alpha Vantage
    3. Inserts the data into the stocks master table
    4. Updates the queue status
    """
    try:
        service = SymbolEnrichmentService()
        results = service.process_missing_symbols(request.batch_size)
        
        logger.info(f"Symbol enrichment completed: {results}")
        return EnrichSymbolsResponse(**results)
        
    except Exception as e:
        logger.error(f"Error in symbol enrichment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/check-missing/{source_table}")
async def check_missing_symbols(source_table: str) -> Dict[str, Any]:
    """
    Check a source table for symbols that are missing from the stocks master table
    and queue them for enrichment.
    
    Supported source tables: earnings_calendar, market_news
    """
    try:
        if source_table not in ['earnings_calendar', 'market_news']:
            raise HTTPException(
                status_code=400, 
                detail="Unsupported source table. Use: earnings_calendar, market_news"
            )
        
        service = SymbolEnrichmentService()
        queued_count = service.check_and_queue_missing_symbols(source_table)
        
        return {
            "source_table": source_table,
            "queued_count": queued_count,
            "message": f"Queued {queued_count} missing symbols for enrichment"
        }
        
    except Exception as e:
        logger.error(f"Error checking missing symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/missing-queue")
async def get_missing_queue_status() -> Dict[str, Any]:
    """Get status of the missing symbols queue."""
    try:
        from app.repositories.stocks_repository import MissingSymbolsRepository
        from app.database import db
        
        # Get queue statistics
        stats_query = """
        SELECT 
            status,
            COUNT(*) as count,
            MIN(discovered_at) as oldest_discovered,
            MAX(discovered_at) as newest_discovered
        FROM missing_symbols_queue 
        GROUP BY status
        ORDER BY status
        """
        
        stats = db.execute_query(stats_query)
        
        # Get recent pending symbols
        recent_query = """
        SELECT symbol, source_table, discovered_at, attempts
        FROM missing_symbols_queue 
        WHERE status = 'pending'
        ORDER BY discovered_at ASC
        LIMIT 20
        """
        
        recent = db.execute_query(recent_query)
        
        return {
            "queue_stats": stats,
            "recent_pending": recent,
            "total_pending": sum(row['count'] for row in stats if row['status'] == 'pending')
        }
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/initialize-stocks-table")
async def initialize_stocks_table() -> Dict[str, Any]:
    """
    Initialize the stocks table and missing_symbols_queue table.
    This should be run once during setup.
    """
    try:
        from app.repositories.stocks_repository import StocksRepository, MissingSymbolsRepository
        
        StocksRepository.create_table()
        MissingSymbolsRepository.create_table()
        
        return {
            "message": "Stocks table and missing symbols queue initialized successfully",
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Error initializing tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))
