"""
Scheduled Job Framework - Industry Standard
Supports cron expressions, intervals, and job management
"""

import logging
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import json
from contextlib import asynccontextmanager

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("scheduler_service")

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class JobType(Enum):
    DATA_COLLECTION = "data_collection"
    CHANGE_DETECTION = "change_detection"
    ALERT_EVALUATION = "alert_evaluation"
    NOTIFICATION_DELIVERY = "notification_delivery"
    MAINTENANCE = "maintenance"

@dataclass
class JobConfig:
    """Job configuration"""
    job_name: str
    job_type: JobType
    cron_expression: Optional[str] = None
    interval_minutes: Optional[int] = None
    timezone: str = "UTC"
    job_config: Dict[str, Any] = None
    is_active: bool = True
    max_retries: int = 3
    timeout_minutes: int = 30

@dataclass
class JobExecution:
    """Job execution context"""
    job_id: str
    execution_id: str
    started_at: datetime
    status: JobStatus
    records_processed: int = 0
    records_failed: int = 0
    alerts_generated: int = 0
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None

class JobScheduler:
    """Main job scheduler with pluggable architecture"""
    
    def __init__(self):
        self.jobs: Dict[str, JobConfig] = {}
        self.job_handlers: Dict[JobType, Callable] = {}
        self.running_jobs: Dict[str, JobExecution] = {}
        self.is_running = False
        
    def register_job_handler(self, job_type: JobType, handler: Callable):
        """Register a job handler for a specific job type"""
        self.job_handlers[job_type] = handler
        logger.info(f"✅ Registered handler for {job_type.value}")
    
    async def load_jobs_from_db(self) -> List[JobConfig]:
        """Load job configurations from database"""
        try:
            query = """
                SELECT job_name, job_type, cron_expression, interval_minutes, 
                       timezone, job_config, is_active
                FROM scheduled_jobs
                WHERE is_active = true
            """
            
            rows = db.execute_query(query)
            jobs = []
            
            for row in rows:
                job_config = JobConfig(
                    job_name=row['job_name'],
                    job_type=JobType(row['job_type']),
                    cron_expression=row.get('cron_expression'),
                    interval_minutes=row.get('interval_minutes'),
                    timezone=row.get('timezone', 'UTC'),
                    job_config=row.get('job_config', {}) or {},
                    is_active=row.get('is_active', True)
                )
                jobs.append(job_config)
                self.jobs[job_config.job_name] = job_config
            
            logger.info(f"✅ Loaded {len(jobs)} jobs from database")
            return jobs
            
        except Exception as e:
            logger.error(f"❌ Error loading jobs from database: {e}")
            return []
    
    def calculate_next_run(self, job: JobConfig, last_run: Optional[datetime] = None) -> datetime:
        """Calculate next run time based on schedule"""
        now = datetime.now(timezone.utc)
        
        if job.interval_minutes:
            # Simple interval scheduling
            if last_run:
                next_run = last_run + timedelta(minutes=job.interval_minutes)
            else:
                next_run = now + timedelta(minutes=job.interval_minutes)
        elif job.cron_expression:
            # TODO: Implement cron parsing (use croniter library)
            # For now, default to hourly
            next_run = now + timedelta(hours=1)
        else:
            # Default to hourly
            next_run = now + timedelta(hours=1)
        
        return next_run
    
    async def execute_job(self, job: JobConfig) -> JobExecution:
        """Execute a job with proper error handling and logging"""
        execution_id = str(uuid.uuid4())
        execution = JobExecution(
            job_id=job.job_name,
            execution_id=execution_id,
            started_at=datetime.now(),
            status=JobStatus.RUNNING
        )
        
        self.running_jobs[job.job_name] = execution
        
        try:
            # Log job start
            await self.log_job_start(job, execution)
            
            # Get job handler
            handler = self.job_handlers.get(job.job_type)
            if not handler:
                raise ValueError(f"No handler registered for {job.job_type}")
            
            # Execute job with timeout
            try:
                result = await asyncio.wait_for(
                    handler(job.job_config, execution),
                    timeout=job.timeout_minutes * 60
                )
                
                # Update execution with results
                if isinstance(result, dict):
                    execution.records_processed = result.get('records_processed', 0)
                    execution.records_failed = result.get('records_failed', 0)
                    execution.alerts_generated = result.get('alerts_generated', 0)
                
                execution.status = JobStatus.COMPLETED
                execution.completed_at = datetime.now()
                
                logger.info(f"✅ Job {job.job_name} completed successfully")
                
            except asyncio.TimeoutError:
                execution.status = JobStatus.FAILED
                execution.error_message = f"Job timed out after {job.timeout_minutes} minutes"
                execution.completed_at = datetime.now()
                
                logger.error(f"❌ Job {job.job_name} timed out")
                
        except Exception as e:
            execution.status = JobStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.now()
            
            logger.error(f"❌ Job {job.job_name} failed: {e}")
        
        finally:
            # Log job completion
            await self.log_job_completion(job, execution)
            
            # Update job statistics
            await self.update_job_stats(job, execution)
            
            # Remove from running jobs
            if job.job_name in self.running_jobs:
                del self.running_jobs[job.job_name]
        
        return execution
    
    async def log_job_start(self, job: JobConfig, execution: JobExecution):
        """Log job start to database"""
        try:
            query = """
                INSERT INTO job_execution_log 
                (job_id, started_at, status)
                VALUES ((SELECT job_id FROM scheduled_jobs WHERE job_name = :job_name), 
                       :started_at, :status)
                RETURNING log_id
            """
            
            params = {
                "job_name": job.job_name,
                "started_at": execution.started_at,
                "status": execution.status.value
            }
            
            result = db.execute_query(query, params)
            if result:
                execution.execution_id = str(result[0]['log_id'])
                
        except Exception as e:
            logger.error(f"❌ Error logging job start: {e}")
    
    async def log_job_completion(self, job: JobConfig, execution: JobExecution):
        """Log job completion to database"""
        try:
            query = """
                UPDATE job_execution_log 
                SET completed_at = :completed_at,
                    duration_ms = :duration_ms,
                    status = :status,
                    records_processed = :records_processed,
                    records_failed = :records_failed,
                    alerts_generated = :alerts_generated,
                    error_message = :error_message
                WHERE log_id = :log_id
            """
            
            duration_ms = None
            if execution.completed_at:
                duration_ms = int((execution.completed_at - execution.started_at).total_seconds() * 1000)
            
            params = {
                "log_id": execution.execution_id,
                "completed_at": execution.completed_at,
                "duration_ms": duration_ms,
                "status": execution.status.value,
                "records_processed": execution.records_processed,
                "records_failed": execution.records_failed,
                "alerts_generated": execution.alerts_generated,
                "error_message": execution.error_message
            }
            
            db.execute_update(query, params)
            
        except Exception as e:
            logger.error(f"❌ Error logging job completion: {e}")
    
    async def update_job_stats(self, job: JobConfig, execution: JobExecution):
        """Update job statistics in database"""
        try:
            query = """
                UPDATE scheduled_jobs 
                SET last_run_at = :last_run_at,
                    next_run_at = :next_run_at,
                    run_count = run_count + 1,
                    success_count = CASE WHEN :status = 'completed' THEN success_count + 1 ELSE success_count END,
                    failure_count = CASE WHEN :status = 'failed' THEN failure_count + 1 ELSE failure_count END,
                    last_duration_ms = :duration_ms,
                    last_error = :error_message
                WHERE job_name = :job_name
            """
            
            params = {
                "job_name": job.job_name,
                "last_run_at": execution.started_at,
                "next_run_at": self.calculate_next_run(job, execution.started_at),
                "status": execution.status.value,
                "duration_ms": int((execution.completed_at - execution.started_at).total_seconds() * 1000) if execution.completed_at else None,
                "error_message": execution.error_message
            }
            
            db.execute_update(query, params)
            
        except Exception as e:
            logger.error(f"❌ Error updating job stats: {e}")
    
    async def start_scheduler(self):
        """Start the job scheduler"""
        if self.is_running:
            logger.warning("⚠️ Scheduler is already running")
            return
        
        self.is_running = True
        logger.info("🚀 Starting job scheduler")
        
        # Load jobs from database
        await self.load_jobs_from_db()
        
        # Start main scheduler loop
        asyncio.create_task(self.scheduler_loop())
    
    async def scheduler_loop(self):
        """Main scheduler loop"""
        while self.is_running:
            try:
                # Check for jobs to run
                for job in self.jobs.values():
                    if not job.is_active:
                        continue
                    
                    # Check if job is already running
                    if job.job_name in self.running_jobs:
                        continue
                    
                    # Get next run time from database
                    next_run = await self.get_next_run_time(job.job_name)
                    if next_run and datetime.now(timezone.utc) >= next_run:
                        # Execute job
                        asyncio.create_task(self.execute_job(job))
                
                # Sleep for a short interval
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"❌ Error in scheduler loop: {e}")
                await asyncio.sleep(30)  # Wait longer on error
    
    async def get_next_run_time(self, job_name: str) -> Optional[datetime]:
        """Get next run time for a job from database"""
        try:
            query = """
                SELECT next_run_at FROM scheduled_jobs 
                WHERE job_name = :job_name AND is_active = true
            """
            
            result = db.execute_query(query, {"job_name": job_name})
            if result:
                return result[0]['next_run_at']
            
        except Exception as e:
            logger.error(f"❌ Error getting next run time: {e}")
        
        return None
    
    async def stop_scheduler(self):
        """Stop the job scheduler"""
        self.is_running = False
        logger.info("🛑 Stopping job scheduler")
        
        # Wait for running jobs to complete (with timeout)
        timeout = 300  # 5 minutes
        start_time = datetime.now()
        
        while self.running_jobs and (datetime.now() - start_time).total_seconds() < timeout:
            await asyncio.sleep(1)
        
        if self.running_jobs:
            logger.warning(f"⚠️ {len(self.running_jobs)} jobs still running after timeout")

# Global scheduler instance
scheduler = JobScheduler()
