from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.investment_scoring_engine import investment_scoring_engine


router = APIRouter(tags=["investment-scores"])


class ComputeInvestmentScoreRequest(BaseModel):
    symbol: str
    as_of_date: date
    scoring_version: str = "v1"
    persist: bool = True


class BulkComputeInvestmentScoresRequest(BaseModel):
    symbols: List[str]
    as_of_date: date
    scoring_version: str = "v1"
    persist: bool = True


@router.post("/investment-scores/compute")
async def compute_investment_score(req: ComputeInvestmentScoreRequest) -> Dict[str, Any]:
    sym = (req.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    row = investment_scoring_engine.compute_for_symbol(
        symbol=sym,
        as_of_date_str=req.as_of_date.isoformat(),
        scoring_version=req.scoring_version,
    )

    if req.persist:
        investment_scoring_engine.upsert(row)

    return {
        "ok": True,
        "row": {
            "symbol": row.symbol,
            "company_name": row.company_name,
            "as_of_date": row.as_of_date,
            "scoring_version": row.scoring_version,
            "business_score": row.business_score,
            "growth_score": row.growth_score,
            "valuation_score": row.valuation_score,
            "technical_score": row.technical_score,
            "investment_score": row.investment_score,
            "business_reason_json": row.business_reason_json,
            "growth_reason_json": row.growth_reason_json,
            "valuation_reason_json": row.valuation_reason_json,
            "technical_reason_json": row.technical_reason_json,
        },
    }


@router.post("/investment-scores/compute-bulk")
async def compute_investment_scores_bulk(req: BulkComputeInvestmentScoresRequest) -> Dict[str, Any]:
    if not req.symbols:
        raise HTTPException(status_code=400, detail="symbols must be non-empty")

    out: Dict[str, Any] = {}
    for s in req.symbols:
        sym = (s or "").strip().upper()
        if not sym:
            continue
        try:
            row = investment_scoring_engine.compute_for_symbol(
                symbol=sym,
                as_of_date_str=req.as_of_date.isoformat(),
                scoring_version=req.scoring_version,
            )
            if req.persist:
                investment_scoring_engine.upsert(row)
            out[sym] = {
                "ok": True,
                "investment_score": row.investment_score,
                "business_score": row.business_score,
                "growth_score": row.growth_score,
                "valuation_score": row.valuation_score,
                "technical_score": row.technical_score,
            }
        except Exception as e:
            out[sym] = {"ok": False, "error": str(e)}

    return {"results": out}


@router.get("/investment-scores/latest")
async def get_latest_investment_score(symbol: str, scoring_version: Optional[str] = None) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    row = investment_scoring_engine.get_latest(symbol=sym, scoring_version=scoring_version)
    if row is None:
        return {"ok": False, "error": "no_data"}
    return {"ok": True, "row": row}


@router.get("/investment-scores/history")
async def get_investment_score_history(symbol: str, limit: int = 60) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=400, detail="symbol must be non-empty")

    rows = investment_scoring_engine.get_history(symbol=sym, limit=int(limit or 60))
    return {"ok": True, "rows": rows}
