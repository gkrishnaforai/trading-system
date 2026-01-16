"""
Bulk Stock Loading API
Endpoint to trigger bulk stock loading operations
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List
import asyncio
from app.config import settings
from app.database import db
import logging

logger = logging.getLogger(__name__)

# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/bulk", tags=["Bulk Operations"])
# CORRECT: router = APIRouter(tags=["Bulk Operations"])
# ========================================
router = APIRouter(tags=["Bulk Operations"])

class BulkLoadRequest(BaseModel):
    symbols: List[str] = []
    batch_size: int = 15
    force_refresh: bool = False

class BulkLoadResponse(BaseModel):
    task_id: str
    message: str
    status: str

# Global task storage (in production, use Redis or database)
bulk_tasks = {}

@router.post("/stocks/load", response_model=BulkLoadResponse)
async def start_bulk_load(request: BulkLoadRequest, background_tasks: BackgroundTasks):
    """Start bulk stock loading in background"""
    try:
        # Import from app services package (industry standard)
        from app.services.bulk_stock_loader import BulkStockLoader
        
        # Generate task ID
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        # Initialize task status
        bulk_tasks[task_id] = {
            'status': 'started',
            'message': 'Bulk stock loading initiated',
            'progress': 0,
            'total': 0,
            'loaded': 0,
            'failed': 0
        }
        
        # Start background task
        background_tasks.add_task(
            run_bulk_load_background,
            task_id,
            request.symbols,
            request.batch_size,
            request.force_refresh
        )
        
        return BulkLoadResponse(
            task_id=task_id,
            message="Bulk stock loading started in background",
            status="started"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stocks/status/{task_id}")
async def get_bulk_load_status(task_id: str):
    """Get status of bulk loading task"""
    if task_id not in bulk_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return bulk_tasks[task_id]

@router.post("/stocks/load/popular")
async def load_popular_stocks(background_tasks: BackgroundTasks):
    """Load popular stocks (predefined list)"""
    try:
        # Import from app services package (industry standard)
        from app.services.bulk_stock_loader import BulkStockLoader
        
        loader = BulkStockLoader()
        symbols = loader.get_popular_stocks()
        
        request = BulkLoadRequest(
            symbols=symbols,
            batch_size=5,  # Reduced batch size to avoid rate limiting
            force_refresh=False
        )
        
        return await start_bulk_load(request, background_tasks)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stocks/database/summary")
async def get_database_summary():
    """Get current database summary"""
    try:
        # Import from app services package (industry standard)
        from app.services.bulk_stock_loader import BulkStockLoader
        
        loader = BulkStockLoader()
        summary = loader.get_database_summary()
        
        return summary
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stocks/popular/list")
async def get_popular_stocks_list():
    """Get list of popular stocks that will be loaded"""
    try:
        # Import from app services package (industry standard)
        from app.services.bulk_stock_loader import BulkStockLoader
        
        loader = BulkStockLoader()
        symbols = loader.get_popular_stocks()
        
        return {
            'total_symbols': len(symbols),
            'symbols': symbols
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_bulk_load_background(task_id: str, symbols: List[str], batch_size: int, force_refresh: bool):
    """Run bulk loading in background"""
    try:
        # Import from app services package (industry standard)
        from app.services.bulk_stock_loader import BulkStockLoader
        
        # Update task status
        bulk_tasks[task_id]['status'] = 'running'
        bulk_tasks[task_id]['message'] = f'Loading {len(symbols)} stocks...'
        bulk_tasks[task_id]['total'] = len(symbols)
        
        loader = BulkStockLoader()
        
        # If force_refresh, delete existing stocks first
        if force_refresh:
            try:
                with loader.engine.connect() as conn:
                    conn.execute(text("DELETE FROM stocks"))
                    conn.commit()
                logger.info("Cleared existing stocks for refresh")
            except Exception as e:
                logger.error(f"Error clearing stocks: {e}")
        
        # Run bulk load
        results = await loader.load_stocks_batch(symbols, batch_size)
        
        # Update final status
        bulk_tasks[task_id].update({
            'status': 'completed',
            'message': 'Bulk loading completed',
            'progress': 100,
            'loaded': results['loaded'],
            'failed': results['failed'],
            'skipped': results.get('skipped', 0),
            'results': results['details'][:20]  # Last 20 details
        })
        
        logger.info(f"Bulk load task {task_id} completed: {results}")
        
    except Exception as e:
        logger.error(f"Bulk load task {task_id} failed: {e}")
        bulk_tasks[task_id].update({
            'status': 'failed',
            'message': f'Bulk loading failed: {str(e)}',
            'error': str(e)
        })

@router.delete("/tasks/{task_id}")
async def cleanup_task(task_id: str):
    """Clean up completed task"""
    if task_id in bulk_tasks:
        del bulk_tasks[task_id]
        return {"message": "Task cleaned up"}
    else:
        raise HTTPException(status_code=404, detail="Task not found")
