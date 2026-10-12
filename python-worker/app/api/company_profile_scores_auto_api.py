from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.company_profile_scores_auto_service import company_profile_scores_auto_service


router = APIRouter(tags=["company-profile-scores-auto"])


class ComputeCompanyProfileAutoRequest(BaseModel):
    symbol: str
    as_of_date: date
    scoring_version: str = "v1"
    persist: bool = True


@router.post("/company-profile-scores/auto/compute")
async def compute_company_profile_scores_auto(req: ComputeCompanyProfileAutoRequest) -> Dict[str, Any]:
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    row = company_profile_scores_auto_service.compute_for_symbol(
        symbol=sym,
        as_of_date_str=req.as_of_date.isoformat(),
        scoring_version=req.scoring_version,
    )
    if req.persist:
        company_profile_scores_auto_service.upsert(row)

    latest = company_profile_scores_auto_service.get_latest_asof(
        symbol=sym,
        as_of_date_str=req.as_of_date.isoformat(),
        scoring_version=req.scoring_version,
    )

    return {"ok": True, "row": latest, "computed": row.__dict__}


@router.get("/company-profile-scores/auto/latest")
async def get_company_profile_scores_auto_latest(
    symbol: str,
    as_of_date: date,
    scoring_version: Optional[str] = None,
) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    row = company_profile_scores_auto_service.get_latest_asof(
        symbol=sym,
        as_of_date_str=as_of_date.isoformat(),
        scoring_version=scoring_version,
    )
    if row is None:
        return {"ok": False, "error": "no_data"}
    return {"ok": True, "row": row}


@router.get("/company-profile-scores/auto/history")
async def get_company_profile_scores_auto_history(symbol: str, limit: int = 60) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    rows = company_profile_scores_auto_service.get_history(symbol=sym, limit=int(limit or 60))
    return {"ok": True, "rows": rows}
