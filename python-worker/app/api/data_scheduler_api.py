"""
Data Refresh Scheduler API
Endpoints for managing automated data refresh scheduling
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.services.data_refresh_scheduler import scheduler
from app.observability.logging import get_logger

logger = get_logger("data_scheduler_api")

# Router
router = APIRouter(tags=["data-scheduler"])

class ScheduleRequest(BaseModel):
    symbol: str = Field(..., description="Stock symbol to schedule")
    data_types: Optional[List[str]] = Field(
        default=["price_historical", "indicators", "fundamentals", "earnings"],
        description="Data types to schedule for refresh"
    )

class ScheduleResponse(BaseModel):
    success: bool
    message: str
    symbol: str
    scheduled_data_types: List[str]

class SchedulerStatusResponse(BaseModel):
    is_running: bool
    total_scheduled: int
    active_schedules: int
    overdue_schedules: int
    next_refresh: Optional[datetime]
    refresh_intervals: Dict[str, int]

@router.post("/start")
async def start_scheduler(background_tasks: BackgroundTasks):
    """Start the data refresh scheduler"""
    try:
        if scheduler.is_running:
            return {"success": False, "message": "Scheduler is already running"}
        
        # Start scheduler in background
        background_tasks.add_task(scheduler.start_scheduler)
        
        logger.info("🚀 Scheduler start requested")
        return {
            "success": True, 
            "message": "Scheduler starting in background",
            "status": "starting"
        }
        
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_scheduler():
    """Stop the data refresh scheduler"""
    try:
        if not scheduler.is_running:
            return {"success": False, "message": "Scheduler is not running"}
        
        await scheduler.stop_scheduler()
        
        logger.info("⏹️ Scheduler stopped")
        return {
            "success": True, 
            "message": "Scheduler stopped successfully",
            "status": "stopped"
        }
        
    except Exception as e:
        logger.error(f"❌ Error stopping scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule", response_model=ScheduleResponse)
async def schedule_symbol_refresh(request: ScheduleRequest):
    """Schedule a symbol for automatic data refresh"""
    try:
        await scheduler.schedule_symbol_refresh(
            symbol=request.symbol,
            data_types=request.data_types
        )
        
        logger.info(f"✅ Scheduled refresh for {request.symbol}")
        
        return ScheduleResponse(
            success=True,
            message=f"Scheduled {request.symbol} for automatic refresh",
            symbol=request.symbol,
            scheduled_data_types=request.data_types
        )
        
    except Exception as e:
        logger.error(f"❌ Error scheduling refresh for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule-all")
async def schedule_all_symbols():
    """Schedule all active symbols for automatic refresh"""
    try:
        # Get all active symbols from stocks table
        from app.database import db
        
        symbols_query = """
        SELECT DISTINCT symbol FROM stocks 
        WHERE is_active = TRUE 
        AND symbol IS NOT NULL
        ORDER BY symbol
        """
        
        result = await db.execute_query(symbols_query)
        symbols = [row['symbol'] for row in result] if result else []
        
        if not symbols:
            return {"success": False, "message": "No active symbols found"}
        
        # Schedule each symbol
        scheduled_count = 0
        for symbol in symbols:
            try:
                await scheduler.schedule_symbol_refresh(symbol)
                scheduled_count += 1
            except Exception as e:
                logger.warning(f"⚠️ Failed to schedule {symbol}: {e}")
        
        logger.info(f"✅ Scheduled {scheduled_count}/{len(symbols)} symbols")
        
        return {
            "success": True,
            "message": f"Scheduled {scheduled_count} out of {len(symbols)} symbols",
            "total_symbols": len(symbols),
            "scheduled_count": scheduled_count
        }
        
    except Exception as e:
        logger.error(f"❌ Error scheduling all symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", response_model=SchedulerStatusResponse)
async def get_scheduler_status():
    """Get current scheduler status"""
    try:
        status = await scheduler.get_schedule_status()
        return SchedulerStatusResponse(**status)
        
    except Exception as e:
        logger.error(f"❌ Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/schedule/{symbol}")
async def remove_symbol_schedule(symbol: str, data_type: Optional[str] = None):
    """Remove a symbol from refresh schedule"""
    try:
        await scheduler.remove_symbol_schedule(symbol, data_type)
        
        message = f"Removed schedule for {symbol}"
        if data_type:
            message += f" ({data_type})"
        
        logger.info(f"✅ {message}")
        
        return {
            "success": True,
            "message": message,
            "symbol": symbol,
            "data_type": data_type
        }
        
    except Exception as e:
        logger.error(f"❌ Error removing schedule for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upcoming")
async def get_upcoming_refreshes(limit: int = 20):
    """Get upcoming scheduled refreshes"""
    try:
        from app.database import db
        
        upcoming_query = """
        SELECT symbol, data_type, next_refresh, refresh_interval
        FROM data_refresh_schedule
        WHERE is_active = TRUE
        ORDER BY next_refresh ASC
        LIMIT :limit
        """
        
        result = await db.execute_query(upcoming_query, {"limit": limit})
        
        return {
            "success": True,
            "upcoming_refreshes": result if result else [],
            "count": len(result) if result else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting upcoming refreshes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_refresh_history(symbol: Optional[str] = None, limit: int = 50):
    """Get refresh history"""
    try:
        # This would require a separate history table
        # For now, return last refresh from schedule table
        from app.database import db
        
        history_query = """
        SELECT symbol, data_type, last_refresh, next_refresh
        FROM data_refresh_schedule
        WHERE is_active = TRUE
        AND last_refresh IS NOT NULL
        """
        
        params = {"limit": limit}
        if symbol:
            history_query += " AND symbol = :symbol"
            params["symbol"] = symbol.upper()
        
        history_query += " ORDER BY last_refresh DESC LIMIT :limit"
        
        result = await db.execute_query(history_query, params)
        
        return {
            "success": True,
            "refresh_history": result if result else [],
            "count": len(result) if result else 0
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting refresh history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
