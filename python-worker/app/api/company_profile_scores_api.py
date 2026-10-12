from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.company_profile_scores_service import CompanyProfileScoreRow, company_profile_scores_service


router = APIRouter(tags=["company-profile-scores"])


class UpsertCompanyProfileScoreRequest(BaseModel):
    symbol: str
    as_of_date: date
    scoring_version: str = "v1"

    moat_score: Optional[float] = None
    leadership_score: Optional[float] = None
    recurring_revenue_score: Optional[float] = None
    ai_optionality_score: Optional[float] = None

    reason_json: Dict[str, Any] = {}


@router.post("/company-profile-scores/upsert")
async def upsert_company_profile_score(req: UpsertCompanyProfileScoreRequest) -> Dict[str, Any]:
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    row = CompanyProfileScoreRow(
        symbol=sym,
        as_of_date=req.as_of_date.isoformat(),
        scoring_version=req.scoring_version,
        moat_score=req.moat_score,
        leadership_score=req.leadership_score,
        recurring_revenue_score=req.recurring_revenue_score,
        ai_optionality_score=req.ai_optionality_score,
        reason_json=req.reason_json or {},
    )

    company_profile_scores_service.upsert(row)
    latest = company_profile_scores_service.get_latest(symbol=sym)
    return {"ok": True, "row": latest}


@router.get("/company-profile-scores/latest")
async def get_company_profile_score_latest(symbol: str, scoring_version: Optional[str] = None) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    row = company_profile_scores_service.get_latest(symbol=sym, scoring_version=scoring_version)
    if row is None:
        return {"ok": False, "error": "no_data"}
    return {"ok": True, "row": row}


@router.get("/company-profile-scores/history")
async def get_company_profile_score_history(symbol: str, limit: int = 60) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    rows = company_profile_scores_service.get_history(symbol=sym, limit=int(limit or 60))
    return {"ok": True, "rows": rows}
