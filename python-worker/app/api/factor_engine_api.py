from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.factor_engine.catalyst_score_engine import CatalystScoreEngine
from app.factor_engine.providers.risk_provider import RiskProvider
from app.factor_engine.providers.technical_provider import TechnicalProvider
from app.factor_engine.entry_score_engine import EntryScoreEngine
from app.factor_engine.screener_configs import list_screener_configs


router = APIRouter(tags=["factor-engine"])


class FactorEngineRiskRequest(BaseModel):
    symbols: List[str]
    as_of_date: Optional[date] = None


class FactorEngineTechnicalRequest(BaseModel):
    symbols: List[str]
    as_of_date: Optional[date] = None


class FactorEngineEntryScoreRequest(BaseModel):
    symbols: List[str]
    as_of_date: Optional[date] = None


class FactorEngineCatalystScoreRequest(BaseModel):
    symbols: List[str]
    as_of_date: Optional[date] = None


@router.post("/factor-engine/risk")
async def factor_engine_risk(request: FactorEngineRiskRequest) -> Dict[str, Any]:
    """Bulk risk factor snapshots for symbols.

    Intended to be called via Go API proxy so UIs continue to talk to Go API only.
    """

    if not request.symbols:
        raise HTTPException(status_code=400, detail="symbols must be non-empty")

    provider = RiskProvider()
    out: Dict[str, Any] = {}

    for sym in request.symbols:
        sym_u = (sym or "").upper().strip()
        if not sym_u:
            continue

        try:
            if request.as_of_date is not None:
                res = provider.get_asof(sym_u, request.as_of_date)
            else:
                res = provider.get_latest(sym_u)

            if res is None:
                out[sym_u] = {"ok": False, "error": "no_data"}
                continue

            out[sym_u] = {
                "ok": True,
                "as_of_date": res.as_of_date.isoformat(),
                "source": res.source,
                "factors": {
                    fid: {
                        "value": snap.value,
                        "confidence": snap.confidence,
                        "source": snap.source,
                    }
                    for fid, snap in res.factors.items()
                },
            }
        except Exception as e:
            out[sym_u] = {"ok": False, "error": str(e)}

    return {"results": out}


@router.post("/factor-engine/catalyst-score")
async def factor_engine_catalyst_score(request: FactorEngineCatalystScoreRequest) -> Dict[str, Any]:
    """Bulk catalyst score outputs for symbols.

    Intended to be called via Go API proxy so UIs continue to talk to Go API only.
    """

    if not request.symbols:
        raise HTTPException(status_code=400, detail="symbols must be non-empty")

    engine = CatalystScoreEngine()
    out: Dict[str, Any] = {}

    for sym in request.symbols:
        sym_u = (sym or "").upper().strip()
        if not sym_u:
            continue

        try:
            if request.as_of_date is not None:
                res = engine.get_asof(sym_u, request.as_of_date)
            else:
                res = engine.get_latest(sym_u)

            if res is None:
                out[sym_u] = {"ok": False, "error": "no_data"}
                continue

            out[sym_u] = {
                "ok": True,
                "as_of_date": res.as_of_date.isoformat(),
                "source": res.source,
                "factors": {
                    fid: {
                        "value": snap.value,
                        "confidence": snap.confidence,
                        "source": snap.source,
                    }
                    for fid, snap in res.factors.items()
                },
            }
        except Exception as e:
            out[sym_u] = {"ok": False, "error": str(e)}

    return {"results": out}


@router.get("/factor-engine/screener-configs")
async def factor_engine_screener_configs() -> Dict[str, Any]:
    return {"configs": list_screener_configs()}


@router.post("/factor-engine/entry-score")
async def factor_engine_entry_score(request: FactorEngineEntryScoreRequest) -> Dict[str, Any]:
    """Bulk entry score outputs for symbols.

    Intended to be called via Go API proxy so UIs continue to talk to Go API only.
    """

    if not request.symbols:
        raise HTTPException(status_code=400, detail="symbols must be non-empty")

    engine = EntryScoreEngine()
    out: Dict[str, Any] = {}

    for sym in request.symbols:
        sym_u = (sym or "").upper().strip()
        if not sym_u:
            continue

        try:
            if request.as_of_date is not None:
                res = engine.get_asof(sym_u, request.as_of_date)
            else:
                res = engine.get_latest(sym_u)

            if res is None:
                out[sym_u] = {"ok": False, "error": "no_data"}
                continue

            out[sym_u] = {
                "ok": True,
                "as_of_date": res.as_of_date.isoformat(),
                "source": res.source,
                "factors": {
                    fid: {
                        "value": snap.value,
                        "confidence": snap.confidence,
                        "source": snap.source,
                    }
                    for fid, snap in res.factors.items()
                },
            }
        except Exception as e:
            out[sym_u] = {"ok": False, "error": str(e)}

    return {"results": out}


@router.post("/factor-engine/technical")
async def factor_engine_technical(request: FactorEngineTechnicalRequest) -> Dict[str, Any]:
    """Bulk technical factor snapshots for symbols.

    Intended to be called via Go API proxy so UIs continue to talk to Go API only.
    """

    if not request.symbols:
        raise HTTPException(status_code=400, detail="symbols must be non-empty")

    provider = TechnicalProvider()
    out: Dict[str, Any] = {}

    for sym in request.symbols:
        sym_u = (sym or "").upper().strip()
        if not sym_u:
            continue

        try:
            if request.as_of_date is not None:
                res = provider.get_asof(sym_u, request.as_of_date)
            else:
                res = provider.get_latest(sym_u)

            if res is None:
                out[sym_u] = {"ok": False, "error": "no_data"}
                continue

            out[sym_u] = {
                "ok": True,
                "as_of_date": res.as_of_date.isoformat(),
                "source": res.source,
                "factors": {
                    fid: {
                        "value": snap.value,
                        "confidence": snap.confidence,
                        "source": snap.source,
                    }
                    for fid, snap in res.factors.items()
                },
            }
        except Exception as e:
            out[sym_u] = {"ok": False, "error": str(e)}

    return {"results": out}
