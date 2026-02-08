"""
Stock Grades API Endpoints
Follows SOLID: Single Responsibility Principle
RESTful API for stock grades and consensus data
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Form
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date

from app.services.stock_grades.service import get_stock_grades_service
from app.services.stock_grades.consensus_service import get_consensus_service as get_consensus_service_instance
from app.services.data_sources.base import DataSourceType
from app.observability.logging import get_logger
from app.database import db
from app.services.universal_alert_service_enhanced import universal_alert_service, UniversalEvent, EntityType

logger = get_logger(__name__)
router = APIRouter(prefix="/grades", tags=["stock-grades"])


# Pydantic models for request/response
class StockGradeResponse(BaseModel):
    id: str
    symbol: str
    grade_date: str
    grading_company: str
    previous_grade: Optional[str]
    new_grade: str
    action: str
    price_at_grade: Optional[float]
    data_source: str

class AnalystDataResponse(BaseModel):
    symbol: str
    ratings: List[Dict[str, Any]]
    price_targets: List[Dict[str, Any]]
    grades: List[Dict[str, Any]]
    fetched_at: str
    created_at: str


class ConsensusResponse(BaseModel):
    symbol: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    consensus_rating: str
    consensus_score: float
    total_analysts: int
    last_updated: str


class RefreshRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of symbols to refresh")
    data_source: str = Field(default="fmp", description="Data source to use")
    include_consensus: bool = Field(default=True, description="Include consensus data")
    force_refresh: bool = Field(default=False, description="Force refresh even if recent data exists")


class RefreshResponse(BaseModel):
    success: bool
    message: str
    results: Dict[str, Any]


class BatchRefreshResponse(BaseModel):
    total_symbols: int
    successful: int
    failed: int
    total_grades_loaded: int
    total_consensus_loaded: int
    errors: List[str]


class CoverageStatsResponse(BaseModel):
    total_symbols: int
    total_firms: int
    total_ratings: int
    upgrades: int
    downgrades: int
    maintains: int
    last_7_days: int


# Dependency injection
async def get_grades_service():
    return get_stock_grades_service()


async def get_consensus_service():
    return get_consensus_service_instance()


# API Endpoints
@router.get("/{symbol}/grades", response_model=List[StockGradeResponse])
async def get_stock_grades(
    symbol: str,
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Maximum number of grades to return"),
    tier1_only: bool = Query(False, description="Only return Tier 1 firm grades"),
    service = Depends(get_grades_service)
):
    """Get stock grades for a symbol"""
    try:
        logger.info(f"📊 Getting grades for {symbol}")
        
        grades = await service.get_grades_for_symbol(symbol, limit, tier1_only)
        
        if not grades:
            raise HTTPException(status_code=404, detail=f"No grades found for {symbol}")
        
        return [StockGradeResponse(**grade) for grade in grades]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting grades for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/consensus", response_model=ConsensusResponse)
async def get_consensus(
    symbol: str,
    service = Depends(get_grades_service)
):
    """Get consensus data for a symbol"""
    try:
        logger.info(f"📊 Getting consensus for {symbol}")
        
        consensus = await service.get_consensus_for_symbol(symbol)
        
        if not consensus:
            raise HTTPException(status_code=404, detail=f"No consensus data found for {symbol}")
        
        return ConsensusResponse(**consensus)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting consensus for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/recent-changes")
async def get_recent_changes(
    symbol: str,
    days: int = Query(7, ge=1, le=365, description="Number of days to look back"),
    service = Depends(get_grades_service)
):
    """Get recent grade changes for a symbol"""
    try:
        logger.info(f"📊 Getting recent changes for {symbol}")
        
        changes = await service.get_recent_changes(symbol, days)
        
        return {
            "symbol": symbol,
            "days": days,
            "changes": changes,
            "count": len(changes)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting recent changes for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/recent-price-target-changes")
async def get_recent_price_target_changes(
    symbol: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    service = Depends(get_grades_service)
):
    """Get recent price target changes for a symbol (DB-backed)"""
    try:
        logger.info(f"📊 Getting recent price target changes for {symbol}")

        changes = await service.get_recent_price_target_changes(symbol, days)

        return {
            "symbol": symbol,
            "days": days,
            "changes": changes,
            "count": len(changes)
        }

    except Exception as e:
        logger.error(f"❌ Error getting recent price target changes for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/consensus-history")
async def get_consensus_history(
    symbol: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    service = Depends(get_grades_service)
):
    """Get consensus history for a symbol"""
    try:
        logger.info(f"📊 Getting consensus history for {symbol}")
        
        history = await service.get_consensus_history(symbol, days)
        
        return {
            "symbol": symbol,
            "days": days,
            "history": history,
            "count": len(history)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting consensus history for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}/analyst-ratings", response_model=AnalystDataResponse)
async def get_analyst_ratings(symbol: str):
    """Get analyst ratings and recommendations for a symbol"""
    try:
        logger.info(f"📊 Getting analyst ratings for {symbol}")
        
        # Import FMP loader for analyst data
        from app.data_sources.fmp.optimized_loader import OptimizedFPMLoader
        optimized_fmp_loader = OptimizedFPMLoader()
        
        ratings = optimized_fmp_loader.get_analyst_ratings(symbol)
        targets = optimized_fmp_loader.get_price_targets(symbol)
        grades = optimized_fmp_loader.get_stock_grades(symbol)
        
        return AnalystDataResponse(
            symbol=symbol,
            ratings=ratings,
            price_targets=targets,
            grades=grades,
            fetched_at=optimized_fmp_loader._get_current_timestamp(),
            created_at=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"❌ Error getting analyst ratings for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest", response_model=Dict[str, Any])
async def get_latest_grades(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    days: int = Query(7, description="Number of days to look back"),
    service = Depends(get_grades_service)
):
    """Get latest stock grades"""
    try:
        logger.info(f"📊 Getting latest grades (symbol={symbol}, days={days})")
        
        grades = await service.get_latest_grades(symbol, days)
        
        return {
            "symbol": symbol,
            "days": days,
            "grades": grades,
            "count": len(grades),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting latest grades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/today-changes", response_model=Dict[str, Any])
async def get_today_grade_changes(service = Depends(get_grades_service)):
    """Get today's stock grade changes (upgrades/downgrades)"""
    try:
        logger.info("📊 Getting today's grade changes")
        
        changes = await service.get_today_changes()
        
        return {
            "date": datetime.now().date().isoformat(),
            "changes": changes,
            "count": len(changes),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting today's grade changes: {e}")
        raise HTTPException(status_code=500, detail=str(e))
async def refresh_symbol_data(
    request: RefreshRequest,
    background_tasks: BackgroundTasks,
    service = Depends(get_grades_service)
):
    """Refresh data for symbols"""
    try:
        logger.info(f"🔄 Refreshing data for {len(request.symbols)} symbols")
        
        if len(request.symbols) > 50:
            raise HTTPException(status_code=400, detail="Too many symbols. Maximum 50 per request.")
        
        # Validate data source
        try:
            data_source = DataSourceType(request.data_source)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid data source: {request.data_source}")
        
        # Refresh data
        results = await service.batch_refresh_symbols(
            request.symbols, 
            data_source, 
            max_concurrent=5
        )
        
        return RefreshResponse(
            success=results['successful'] > 0,
            message=f"Processed {len(request.symbols)} symbols: {results['successful']} successful, {results['failed']} failed",
            results=results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error refreshing data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh/{symbol}", response_model=RefreshResponse)
async def refresh_single_symbol(
    symbol: str,
    background_tasks: BackgroundTasks,
    data_source: str = Query(default="fmp"),
    include_consensus: bool = Query(default=True),
    force_refresh: bool = Query(default=False),
    service = Depends(get_grades_service)
):
    """Refresh data for a single symbol"""
    try:
        logger.info(f"🔄 Refreshing data for {symbol}")

        sym = str(symbol).strip().upper()

        prev_grades_by_key: Dict[tuple, Dict[str, Any]] = {}
        try:
            prev_rows = db.execute_query(
                """
                SELECT grading_company, grade_date, data_source,
                       previous_grade, new_grade, action, price_at_grade
                FROM stock_grades
                WHERE symbol = :symbol
                """,
                {"symbol": sym},
            )
            for r in prev_rows or []:
                row = dict(r)
                key = (
                    row.get('grading_company'),
                    row.get('grade_date'),
                    row.get('data_source') or 'unknown',
                )
                prev_grades_by_key[key] = row
        except Exception:
            prev_grades_by_key = {}

        prev_consensus = None
        if include_consensus:
            try:
                prev_consensus = await service.get_consensus_for_symbol(sym)
            except Exception:
                prev_consensus = None

        prev_pt_row = None
        try:
            prev_rows = db.execute_query(
                """
                SELECT id, symbol, old_price_target, new_price_target, old_rating, new_rating,
                       rating_score, change_type, data_source, created_at
                FROM rating_change_log
                WHERE symbol = :symbol
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"symbol": sym},
            )
            if prev_rows:
                prev_pt_row = dict(prev_rows[0])
        except Exception:
            prev_pt_row = None
        
        # Validate data source
        try:
            source_type = DataSourceType(data_source)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid data source: {data_source}")
        
        # Refresh data
        result = await service.refresh_symbol_data(
            sym, 
            source_type, 
            include_consensus
        )

        try:
            grades = result.get('grades') or []
            for g in grades:
                gd = getattr(g, 'grade_date', None)

                grading_company = getattr(g, 'grading_company', None)
                grade_data_source = getattr(g, 'data_source', None) or 'unknown'
                grade_key = (grading_company, gd, grade_data_source)

                prev = prev_grades_by_key.get(grade_key)
                prev_prev_grade = prev.get('previous_grade') if isinstance(prev, dict) else None
                prev_new_grade = prev.get('new_grade') if isinstance(prev, dict) else None
                prev_action = prev.get('action') if isinstance(prev, dict) else None
                prev_price_at_grade = prev.get('price_at_grade') if isinstance(prev, dict) else None

                curr_prev_grade = getattr(g, 'previous_grade', None)
                curr_new_grade = getattr(g, 'new_grade', None)
                curr_action = getattr(g, 'action', None)
                curr_price_at_grade = getattr(g, 'price_at_grade', None)

                is_new = prev is None
                is_changed = (
                    (prev_prev_grade != curr_prev_grade)
                    or (prev_new_grade != curr_new_grade)
                    or (prev_action != curr_action)
                    or (prev_price_at_grade != curr_price_at_grade)
                )

                if not (is_new or is_changed):
                    continue

                event = UniversalEvent(
                    event_type='grade_change',
                    entity_type=EntityType.STOCK,
                    entity_id=sym,
                    event_data={
                        'symbol': sym,
                        'company_name': '',
                        'rating': curr_new_grade,
                        'rating_score': None,
                        'previous_rating': curr_prev_grade,
                        'previous_rating_score': None,
                        'rating_change_date': gd.isoformat() if hasattr(gd, 'isoformat') else (str(gd) if gd is not None else None),
                        'analyst_company': grading_company,
                        'source': grade_data_source,
                        'change_type': curr_action,
                        'price_at_grade': curr_price_at_grade,
                    },
                    event_timestamp=datetime.utcnow(),
                    data_source='grades_refresh',
                    confidence_score=1.0,
                    tags=['ingestion', 'immediate']
                )
                await universal_alert_service.event_repo.save_event(event)

            if include_consensus:
                new_consensus = None
                try:
                    new_consensus = await service.get_consensus_for_symbol(sym)
                except Exception:
                    new_consensus = None

                prev_rating = (prev_consensus or {}).get('consensus_rating') if isinstance(prev_consensus, dict) else None
                new_rating = (new_consensus or {}).get('consensus_rating') if isinstance(new_consensus, dict) else None
                if new_consensus and prev_rating != new_rating:
                    total_analysts = 0
                    for k in ['strong_buy', 'buy', 'hold', 'sell', 'strong_sell']:
                        try:
                            total_analysts += int(new_consensus.get(k) or 0)
                        except Exception:
                            pass

                    ce = UniversalEvent(
                        event_type='consensus_update',
                        entity_type=EntityType.STOCK,
                        entity_id=sym,
                        event_data={
                            'symbol': sym,
                            'previous_consensus': prev_rating,
                            'new_consensus': new_rating,
                            'total_analysts': total_analysts,
                            'distribution': {
                                'strong_buy': new_consensus.get('strong_buy'),
                                'buy': new_consensus.get('buy'),
                                'hold': new_consensus.get('hold'),
                                'sell': new_consensus.get('sell'),
                                'strong_sell': new_consensus.get('strong_sell'),
                            },
                            'source': 'grades_refresh',
                        },
                        event_timestamp=datetime.utcnow(),
                        data_source='grades_refresh',
                        confidence_score=1.0,
                        tags=['ingestion', 'immediate']
                    )
                    await universal_alert_service.event_repo.save_event(ce)

            new_pt_row = None
            try:
                new_rows = db.execute_query(
                    """
                    SELECT id, symbol, old_price_target, new_price_target, old_rating, new_rating,
                           rating_score, change_type, data_source, created_at
                    FROM rating_change_log
                    WHERE symbol = :symbol
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    {"symbol": sym},
                )
                if new_rows:
                    new_pt_row = dict(new_rows[0])
            except Exception:
                new_pt_row = None

            prev_pt_id = prev_pt_row.get('id') if isinstance(prev_pt_row, dict) else None
            new_pt_id = new_pt_row.get('id') if isinstance(new_pt_row, dict) else None
            if new_pt_row and (prev_pt_id != new_pt_id):
                pe = UniversalEvent(
                    event_type='price_target_change',
                    entity_type=EntityType.STOCK,
                    entity_id=sym,
                    event_data={
                        'symbol': sym,
                        'old_price_target': new_pt_row.get('old_price_target'),
                        'new_price_target': new_pt_row.get('new_price_target'),
                        'old_rating': new_pt_row.get('old_rating'),
                        'new_rating': new_pt_row.get('new_rating'),
                        'rating_score': new_pt_row.get('rating_score'),
                        'change_type': new_pt_row.get('change_type'),
                        'source': new_pt_row.get('data_source') or 'local_db',
                        'created_at': new_pt_row.get('created_at').isoformat() if hasattr(new_pt_row.get('created_at'), 'isoformat') else None,
                    },
                    event_timestamp=datetime.utcnow(),
                    data_source='grades_refresh',
                    confidence_score=1.0,
                    tags=['ingestion', 'immediate']
                )
                await universal_alert_service.event_repo.save_event(pe)
        except Exception as e:
            logger.warning(f"⚠️ Failed to emit universal alert events for {sym}: {e}")
        
        return RefreshResponse(
            success=len(result.get('errors', [])) == 0,
            message=f"Grades loaded: {result.get('grades_loaded', 0)}, Consensus loaded: {result.get('consensus_loaded', False)}",
            results=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error refreshing {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-consensus/{symbol}")
async def update_consensus(
    symbol: str,
    background_tasks: BackgroundTasks,
    consensus_service = Depends(get_consensus_service)
):
    """Update consensus data for a symbol"""
    try:
        logger.info(f"🔄 Updating consensus for {symbol}")
        
        # Use the stock grades refresh endpoint instead, which includes consensus
        # This avoids the async/await issue with the consensus service
        grades_service = get_stock_grades_service()
        
        # Load fresh data which will update consensus
        from app.services.data_sources.base import DataSourceType
        result = await grades_service.load_consensus_for_symbol(symbol, DataSourceType.FMP)
        
        return {
            "symbol": symbol,
            "success": True,
            "result": result,
            "message": f"Consensus updated for {symbol}"
        }
        
    except Exception as e:
        logger.error(f"❌ Error updating consensus for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/recent-changes")
async def get_symbols_with_recent_changes(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    service = Depends(get_grades_service)
):
    """Get symbols with recent grade changes"""
    try:
        logger.info(f"📊 Getting symbols with recent changes")
        
        symbols = await service.get_symbols_with_recent_changes(days)
        
        return {
            "days": days,
            "symbols": symbols,
            "count": len(symbols)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting symbols with recent changes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coverage-stats", response_model=CoverageStatsResponse)
async def get_coverage_stats(service = Depends(get_grades_service)):
    """Get overall coverage statistics"""
    try:
        logger.info("📊 Getting coverage statistics")
        
        stats = await service.get_coverage_stats()
        
        if not stats:
            return CoverageStatsResponse(
                total_symbols=0,
                total_firms=0,
                total_ratings=0,
                upgrades=0,
                downgrades=0,
                maintains=0,
                last_7_days=0
            )
        
        return CoverageStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"❌ Error getting coverage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/data-sources")
async def get_data_sources(service = Depends(get_grades_service)):
    """Get available data sources and their status"""
    try:
        logger.info("📊 Getting data sources info")
        
        info = await service.get_data_source_info()
        validation = await service.validate_data_sources()
        
        return {
            "available_sources": list(info.keys()),
            "source_info": info,
            "validation_results": validation
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting data sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-update-consensus")
async def batch_update_consensus(
    background_tasks: BackgroundTasks,
    symbols: List[str] = Query(...),
    consensus_service = Depends(get_consensus_service)
):
    """Batch update consensus for multiple symbols"""
    try:
        logger.info(f"🔄 Batch updating consensus for {len(symbols)} symbols")
        
        if len(symbols) > 100:
            raise HTTPException(status_code=400, detail="Too many symbols. Maximum 100 per batch.")
        
        results = await consensus_service.batch_update_consensus(symbols, max_concurrent=3)
        
        return {
            "success": results['successful'] > 0,
            "message": f"Processed {len(symbols)} symbols: {results['successful']} successful, {results['failed']} failed",
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in batch consensus update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/consensus-summary")
async def get_consensus_change_summary(
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    consensus_service = Depends(get_consensus_service)
):
    """Get summary of recent consensus changes"""
    try:
        logger.info("📊 Getting consensus change summary")
        
        summary = await consensus_service.get_consensus_change_summary(days)
        
        return summary
        
    except Exception as e:
        logger.error(f"❌ Error getting consensus summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
