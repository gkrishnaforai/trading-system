"""
Fundamentals Scheduler API Endpoints
API endpoints for managing daily fundamentals data collection scheduler
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime

from app.services.fundamentals_scheduler import (
    fundamentals_scheduler, 
    start_fundamentals_scheduler, 
    stop_fundamentals_scheduler,
    get_fundamentals_scheduler_status
)
from app.observability.logging import get_logger

logger = get_logger("fundamentals_scheduler_api")

router = APIRouter(tags=["fundamentals-scheduler"])

class SchedulerStatusResponse(BaseModel):
    """Response model for scheduler status"""
    running: bool
    timezone: str
    jobs: list
    total_jobs: int

class SchedulerActionResponse(BaseModel):
    """Response model for scheduler actions"""
    success: bool
    message: str
    timestamp: datetime

@router.post("/start", response_model=SchedulerActionResponse)
async def start_fundamentals_scheduler_api(background_tasks: BackgroundTasks):
    """Start the fundamentals scheduler"""
    try:
        if fundamentals_scheduler.running:
            return SchedulerActionResponse(
                success=False,
                message="Fundamentals scheduler is already running",
                timestamp=datetime.now()
            )
        
        # Start scheduler in background
        background_tasks.add_task(start_fundamentals_scheduler)
        
        logger.info("🚀 Fundamentals scheduler start requested")
        return SchedulerActionResponse(
            success=True,
            message="Fundamentals scheduler start initiated",
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"❌ Error starting fundamentals scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop", response_model=SchedulerActionResponse)
async def stop_fundamentals_scheduler_api():
    """Stop the fundamentals scheduler"""
    try:
        if not fundamentals_scheduler.running:
            return SchedulerActionResponse(
                success=False,
                message="Fundamentals scheduler is not running",
                timestamp=datetime.now()
            )
        
        await stop_fundamentals_scheduler()
        
        logger.info("⏹️ Fundamentals scheduler stopped")
        return SchedulerActionResponse(
            success=True,
            message="Fundamentals scheduler stopped successfully",
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"❌ Error stopping fundamentals scheduler: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status", response_model=SchedulerStatusResponse)
async def get_fundamentals_scheduler_status_api():
    """Get current fundamentals scheduler status"""
    try:
        status = get_fundamentals_scheduler_status()
        return SchedulerStatusResponse(**status)
        
    except Exception as e:
        logger.error(f"❌ Error getting fundamentals scheduler status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trigger-morning")
async def trigger_morning_collection(background_tasks: BackgroundTasks):
    """Manually trigger the morning fundamentals collection"""
    try:
        # Trigger morning collection in background
        background_tasks.add_task(
            fundamentals_scheduler.run_fundamentals_collection, 
            "manual-morning"
        )
        
        logger.info("🔄 Manual morning fundamentals collection triggered")
        return {
            "success": True,
            "message": "Morning fundamentals collection triggered",
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Error triggering morning collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trigger-evening")
async def trigger_evening_collection(background_tasks: BackgroundTasks):
    """Manually trigger the evening fundamentals collection"""
    try:
        # Trigger evening collection in background
        background_tasks.add_task(
            fundamentals_scheduler.run_fundamentals_collection, 
            "manual-evening"
        )
        
        logger.info("🔄 Manual evening fundamentals collection triggered")
        return {
            "success": True,
            "message": "Evening fundamentals collection triggered",
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Error triggering evening collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/next-runs")
async def get_next_scheduled_runs():
    """Get next scheduled run times"""
    try:
        status = get_fundamentals_scheduler_status()
        next_runs = []
        
        for job in status['jobs']:
            if job['next_run']:
                next_runs.append({
                    'job_id': job['id'],
                    'job_name': job['name'],
                    'next_run_time': job['next_run'],
                    'trigger': job['trigger']
                })
        
        return {
            "next_runs": next_runs,
            "scheduler_running": status['running'],
            "timezone": status['timezone']
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting next run times: {e}")
        raise HTTPException(status_code=500, detail=str(e))
