from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db_storage.repositories import get_database_service
from app.services.macro_engine import MacroOrchestrator


router = APIRouter(tags=["macro-engine"])


class MacroRunRequest(BaseModel):
    as_of_date: Optional[date] = Field(default=None)


@router.post("/macro/run")
def run_macro(request: MacroRunRequest) -> Dict[str, Any]:
    """Run daily macro recomputation (only writes a snapshot if new FRED data is detected)."""
    try:
        orchestrator = MacroOrchestrator()
        res = orchestrator.run_daily(as_of_date=request.as_of_date)
        return {
            "ok": res.ok,
            "as_of_date": res.as_of_date.isoformat(),
            "updated_series": res.updated_series,
            "snapshot_written": res.snapshot_written,
            "message": res.message,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/latest")
def get_latest_macro_snapshot() -> Dict[str, Any]:
    db = get_database_service()
    snap = db.macro_snapshots.get_latest_snapshot()
    if not snap:
        return {"ok": False, "snapshot": None}
    return {"ok": True, "snapshot": snap}


@router.get("/macro/snapshots")
def get_macro_snapshots(days: int = 540) -> Dict[str, Any]:
    if days <= 0 or days > 3650:
        raise HTTPException(status_code=400, detail="days out of range")

    db = get_database_service()
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    snaps = db.macro_snapshots.get_snapshots(start_date=start, end_date=end)
    return {"ok": True, "start_date": start.isoformat(), "end_date": end.isoformat(), "snapshots": snaps}
