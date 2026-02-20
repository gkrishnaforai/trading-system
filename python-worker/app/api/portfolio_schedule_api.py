"""
Portfolio Schedule Management API
Comprehensive CRUD operations for portfolio analysis schedules
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, time
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import uuid

from app.database import get_db
from app.observability.logging import get_logger
from app.services.portfolio_scheduler import portfolio_scheduler

logger = get_logger("portfolio_schedule_api")
router = APIRouter(tags=["portfolio-schedules"])

# Pydantic Models
class ScheduleCreate(BaseModel):
    portfolio_id: str = Field(..., description="Portfolio ID")
    schedule_type: str = Field(..., pattern="^(daily|weekly|monthly)$")
    schedule_time: str = Field(..., description="Time in HH:MM format")
    schedule_day: Optional[int] = Field(None, ge=1, le=31, description="Day of month (1-31) for monthly, day of week (1-7) for weekly")
    notification_preferences: Dict[str, bool] = Field(default={"push": False, "email": True})

class ScheduleUpdate(BaseModel):
    schedule_type: Optional[str] = Field(None, pattern="^(daily|weekly|monthly)$")
    schedule_time: Optional[str] = Field(None, description="Time in HH:MM format")
    schedule_day: Optional[int] = Field(None, ge=1, le=31)
    notification_preferences: Optional[Dict[str, bool]] = None
    is_active: Optional[bool] = None

class ScheduleResponse(BaseModel):
    id: str
    portfolio_id: str
    portfolio_name: str
    user_id: str
    username: str
    user_email: str
    schedule_type: str
    schedule_time: str
    schedule_day: Optional[int]
    is_active: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    notification_preferences: Dict[str, bool]
    created_at: datetime
    updated_at: datetime
    job_status: str  # 'scheduled', 'running', 'paused', 'error'

class ScheduleListResponse(BaseModel):
    schedules: List[ScheduleResponse]
    total_count: int
    active_count: int
    paused_count: int
    running_count: int

@router.get("/list", response_model=ScheduleListResponse)
async def list_schedules(
    status: Optional[str] = Query(None, pattern="^(active|paused|all)$", description="Filter by status"),
    portfolio_id: Optional[str] = None,
    user_id: Optional[str] = None
):
    """
    List all portfolio schedules with filtering options
    
    Args:
        status: Filter by schedule status (active, paused, all)
        portfolio_id: Filter by specific portfolio
        user_id: Filter by specific user
    
    Returns:
        List of schedules with counts
    """
    try:
        db = get_db()
        
        # Build WHERE clause
        where_conditions = []
        params = {}
        
        if status == "active":
            where_conditions.append("sa.is_active = true")
        elif status == "paused":
            where_conditions.append("sa.is_active = false")
        
        if portfolio_id:
            where_conditions.append("sa.portfolio_id = :portfolio_id")
            params["portfolio_id"] = portfolio_id
            
        if user_id:
            where_conditions.append("sa.user_id = :user_id")
            params["user_id"] = user_id
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Query schedules
        query = f"""
            SELECT sa.id, sa.portfolio_id, sa.user_id, sa.schedule_type,
                   sa.schedule_time, sa.schedule_day, sa.is_active,
                   sa.last_run, sa.next_run, sa.notification_preferences,
                   sa.created_at, sa.updated_at,
                   p.name as portfolio_name, u.username, u.email as user_email
            FROM scheduled_analyses sa
            JOIN portfolios p ON sa.portfolio_id = p.id
            JOIN users u ON sa.user_id = u.id
            {where_clause}
            ORDER BY sa.created_at DESC
        """
        
        schedules_data = db.execute(query, params).fetchall()
        
        # Get job status from scheduler
        schedules = []
        active_count = 0
        paused_count = 0
        running_count = 0
        
        for schedule in schedules_data:
            job_id = f"portfolio_{schedule['portfolio_id']}_{schedule['id']}"
            job = portfolio_scheduler.scheduler.get_job(job_id) if portfolio_scheduler.running else None
            
            job_status = "paused" if not schedule['is_active'] else (
                "running" if job and job.pending else (
                    "scheduled" if job else "error"
                )
            )
            
            if schedule['is_active']:
                active_count += 1
            else:
                paused_count += 1
                
            if job_status == "running":
                running_count += 1
            
            schedules.append(ScheduleResponse(
                id=str(schedule['id']),
                portfolio_id=str(schedule['portfolio_id']),
                portfolio_name=schedule['portfolio_name'],
                user_id=str(schedule['user_id']),
                username=schedule['username'],
                user_email=schedule['user_email'],
                schedule_type=schedule['schedule_type'],
                schedule_time=str(schedule['schedule_time']),
                schedule_day=schedule['schedule_day'],
                is_active=schedule['is_active'],
                last_run=schedule['last_run'],
                next_run=schedule['next_run'],
                notification_preferences=schedule['notification_preferences'] or {"push": False, "email": True},
                created_at=schedule['created_at'],
                updated_at=schedule['updated_at'],
                job_status=job_status
            ))
        
        return ScheduleListResponse(
            schedules=schedules,
            total_count=len(schedules),
            active_count=active_count,
            paused_count=paused_count,
            running_count=running_count
        )
        
    except Exception as e:
        logger.error(f"❌ Error listing schedules: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str):
    """Get a specific schedule by ID"""
    try:
        db = get_db()
        
        schedule = db.execute(
            """
            SELECT sa.id, sa.portfolio_id, sa.user_id, sa.schedule_type,
                   sa.schedule_time, sa.schedule_day, sa.is_active,
                   sa.last_run, sa.next_run, sa.notification_preferences,
                   sa.created_at, sa.updated_at,
                   p.name as portfolio_name, u.username, u.email as user_email
            FROM scheduled_analyses sa
            JOIN portfolios p ON sa.portfolio_id = p.id
            JOIN users u ON sa.user_id = u.id
            WHERE sa.id = :schedule_id
            """,
            {"schedule_id": schedule_id}
        ).fetchone()
        
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Get job status
        job_id = f"portfolio_{schedule['portfolio_id']}_{schedule['id']}"
        job = portfolio_scheduler.scheduler.get_job(job_id) if portfolio_scheduler.running else None
        
        job_status = "paused" if not schedule['is_active'] else (
            "running" if job and job.pending else (
                "scheduled" if job else "error"
            )
        )
        
        return ScheduleResponse(
            id=str(schedule['id']),
            portfolio_id=str(schedule['portfolio_id']),
            portfolio_name=schedule['portfolio_name'],
            user_id=str(schedule['user_id']),
            username=schedule['username'],
            user_email=schedule['user_email'],
            schedule_type=schedule['schedule_type'],
            schedule_time=str(schedule['schedule_time']),
            schedule_day=schedule['schedule_day'],
            is_active=schedule['is_active'],
            last_run=schedule['last_run'],
            next_run=schedule['next_run'],
            notification_preferences=schedule['notification_preferences'] or {"push": False, "email": True},
            created_at=schedule['created_at'],
            updated_at=schedule['updated_at'],
            job_status=job_status
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting schedule {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=ScheduleResponse)
async def create_schedule(schedule_data: ScheduleCreate, background_tasks: BackgroundTasks):
    """Create a new portfolio schedule"""
    try:
        db = get_db()
        
        # Parse time
        try:
            schedule_time_obj = datetime.strptime(schedule_data.schedule_time, '%H:%M').time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")
        
        # Create schedule
        schedule_id = db.execute(
            """
            INSERT INTO scheduled_analyses 
            (portfolio_id, user_id, schedule_type, schedule_time, schedule_day, notification_preferences)
            VALUES (:portfolio_id, 
                    (SELECT user_id FROM portfolios WHERE id = :portfolio_id),
                    :schedule_type, :schedule_time, :schedule_day, :notification_preferences)
            RETURNING id
            """,
            {
                "portfolio_id": schedule_data.portfolio_id,
                "schedule_type": schedule_data.schedule_type,
                "schedule_time": schedule_time_obj,
                "schedule_day": schedule_data.schedule_day,
                "notification_preferences": schedule_data.notification_preferences
            }
        ).fetchone()['id']
        
        # Reload scheduler if running
        if portfolio_scheduler.running:
            await portfolio_scheduler.load_schedules_from_db()
        
        # Return created schedule
        return await get_schedule(str(schedule_id))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(schedule_id: str, schedule_data: ScheduleUpdate):
    """Update an existing schedule"""
    try:
        db = get_db()
        
        # Check if schedule exists
        existing = db.execute(
            "SELECT id FROM scheduled_analyses WHERE id = :schedule_id",
            {"schedule_id": schedule_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Build update query
        update_fields = []
        params = {"schedule_id": schedule_id}
        
        if schedule_data.schedule_type:
            update_fields.append("schedule_type = :schedule_type")
            params["schedule_type"] = schedule_data.schedule_type
            
        if schedule_data.schedule_time:
            try:
                schedule_time_obj = datetime.strptime(schedule_data.schedule_time, '%H:%M').time()
                update_fields.append("schedule_time = :schedule_time")
                params["schedule_time"] = schedule_time_obj
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")
                
        if schedule_data.schedule_day is not None:
            update_fields.append("schedule_day = :schedule_day")
            params["schedule_day"] = schedule_data.schedule_day
            
        if schedule_data.notification_preferences is not None:
            update_fields.append("notification_preferences = :notification_preferences")
            params["notification_preferences"] = schedule_data.notification_preferences
            
        if schedule_data.is_active is not None:
            update_fields.append("is_active = :is_active")
            params["is_active"] = schedule_data.is_active
        
        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            query = f"""
                UPDATE scheduled_analyses 
                SET {', '.join(update_fields)}
                WHERE id = :schedule_id
            """
            db.execute(query, params)
        
        # Reload scheduler if running
        if portfolio_scheduler.running:
            await portfolio_scheduler.load_schedules_from_db()
        
        # Return updated schedule
        return await get_schedule(schedule_id)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating schedule {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule"""
    try:
        db = get_db()
        
        # Check if schedule exists
        existing = db.execute(
            "SELECT id, portfolio_id FROM scheduled_analyses WHERE id = :schedule_id",
            {"schedule_id": schedule_id}
        ).fetchone()
        
        if not existing:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Remove from scheduler first
        job_id = f"portfolio_{existing['portfolio_id']}_{schedule_id}"
        if portfolio_scheduler.running and portfolio_scheduler.scheduler.get_job(job_id):
            portfolio_scheduler.scheduler.remove_job(job_id)
        
        # Delete from database
        db.execute(
            "DELETE FROM scheduled_analyses WHERE id = :schedule_id",
            {"schedule_id": schedule_id}
        )
        
        return {"success": True, "message": "Schedule deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting schedule {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str):
    """Toggle schedule active/paused status"""
    try:
        db = get_db()
        
        # Get current status
        schedule = db.execute(
            "SELECT id, portfolio_id, is_active FROM scheduled_analyses WHERE id = :schedule_id",
            {"schedule_id": schedule_id}
        ).fetchone()
        
        if not schedule:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        # Toggle status
        new_status = not schedule['is_active']
        db.execute(
            "UPDATE scheduled_analyses SET is_active = :is_active, updated_at = CURRENT_TIMESTAMP WHERE id = :schedule_id",
            {"is_active": new_status, "schedule_id": schedule_id}
        )
        
        # Reload scheduler if running
        if portfolio_scheduler.running:
            await portfolio_scheduler.load_schedules_from_db()
        
        return {
            "success": True, 
            "message": f"Schedule {'activated' if new_status else 'paused'} successfully",
            "is_active": new_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error toggling schedule {schedule_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/overview")
async def get_schedule_overview():
    """Get overview of all schedules status"""
    try:
        db = get_db()
        
        # Get counts by status
        status_counts = db.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN is_active = true THEN 1 END) as active,
                COUNT(CASE WHEN is_active = false THEN 1 END) as paused,
                COUNT(CASE WHEN last_run IS NOT NULL THEN 1 END) as has_run,
                COUNT(CASE WHEN next_run > CURRENT_TIMESTAMP THEN 1 END) as upcoming
            FROM scheduled_analyses
        """).fetchone()
        
        # Get schedule type distribution
        type_distribution = db.execute("""
            SELECT schedule_type, COUNT(*) as count
            FROM scheduled_analyses
            GROUP BY schedule_type
        """).fetchall()
        
        # Get recent runs
        recent_runs = db.execute("""
            SELECT sa.id, p.name as portfolio_name, sa.last_run, sa.is_active
            FROM scheduled_analyses sa
            JOIN portfolios p ON sa.portfolio_id = p.id
            WHERE sa.last_run IS NOT NULL
            ORDER BY sa.last_run DESC
            LIMIT 10
        """).fetchall()
        
        return {
            "scheduler_running": portfolio_scheduler.running,
            "total_schedules": status_counts['total'],
            "active_schedules": status_counts['active'],
            "paused_schedules": status_counts['paused'],
            "schedules_with_runs": status_counts['has_run'],
            "upcoming_runs": status_counts['upcoming'],
            "type_distribution": {row['schedule_type']: row['count'] for row in type_distribution},
            "recent_runs": [
                {
                    "schedule_id": str(row['id']),
                    "portfolio_name": row['portfolio_name'],
                    "last_run": row['last_run'],
                    "is_active": row['is_active']
                }
                for row in recent_runs
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting schedule overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))
