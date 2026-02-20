"""
Worker Run Endpoint (DRY orchestration)
Accepts run_id + profile_name + symbols from Go API and executes the profile.
Emits change events and updates run status.
"""
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional

from app.ingestion.profiles import get_profile
from app.database import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worker", tags=["worker"])

class WorkerRunRequest(BaseModel):
    run_id: str = Field(..., description="Run ID from Go API")
    profile_name: str = Field(..., description="Ingestion profile name")
    symbols: Optional[List[str]] = Field(default=None, description="Symbols to process (overrides profile defaults)")

@router.post("/run")
async def run_profile(request: WorkerRunRequest, background_tasks: BackgroundTasks):
    """
    Execute an ingestion profile by name under a given run_id.
    This endpoint is called by Go API to trigger ingestion.
    """
    try:
        profile = get_profile(request.profile_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Run in background so Go API gets fast 202 Accepted
    background_tasks.add_task(_execute_profile, profile, request.run_id, request.symbols)
    return {"run_id": request.run_id, "status": "accepted", "profile_name": request.profile_name}

async def _execute_profile(profile, run_id: str, symbols: Optional[List[str]]):
    """Background task to execute the profile and update run status."""
    try:
        # Update run status to running
        _update_run_status(run_id, "running")
        # Execute the profile (this emits change events)
        summary = profile.execute(run_id, symbols)
        # Update run status to completed
        _update_run_status(run_id, "completed")
        logger.info(f"[{run_id}] Completed profile {profile.name}: {summary}")
    except Exception as e:
        logger.exception(f"[{run_id}] Failed to execute profile {profile.name}")
        _update_run_status(run_id, "failed")

def _update_run_status(run_id: str, status: str):
    """Update run status in data_ingestion_runs."""
    query = """
        UPDATE data_ingestion_runs
        SET status = %s,
            finished_at = CASE WHEN %s IN ('completed', 'failed') THEN NOW() ELSE finished_at END
        WHERE run_id = %s
    """
    with db.cursor() as cur:
        cur.execute(query, (status, status, run_id))
        db.commit()
