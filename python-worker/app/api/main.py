"""
Main API Endpoints for Trading System
Provides core functionality endpoints
"""
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.database import db
from app.data_management.refresh_manager import DataRefreshManager, DataType
from app.services.indicator_service import IndicatorService
from app.services.strategy_service import StrategyService
from app.observability.logging import get_logger

logger = get_logger("main_api")

router = APIRouter(tags=["main"])

# Request/Response Models
class RefreshRequest(BaseModel):
    symbols: List[str]
    data_types: List[str]
    force: bool = False

class RefreshResponse(BaseModel):
    success: bool
    message: str
    results: Dict[str, Any]


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_data(request: RefreshRequest, background_tasks: BackgroundTasks):
    """Trigger data refresh for specific symbols and data types"""
    try:
        refresh_manager = DataRefreshManager()
        
        # Convert string data types to DataType enum
        data_type_mapping = {
            "price_historical": DataType.PRICE_HISTORICAL,
            "price_current": DataType.PRICE_CURRENT,
            "fundamentals": DataType.FUNDAMENTALS,
            "indicators": DataType.INDICATORS,
            "news": DataType.NEWS,
            "earnings": DataType.EARNINGS,
            "industry_peers": DataType.INDUSTRY_PEERS
        }
        
        results = {}
        successful_count = 0
        failed_count = 0
        
        for symbol in request.symbols:
            try:
                # Convert data types
                data_types = []
                for dt in request.data_types:
                    if dt in data_type_mapping:
                        data_types.append(data_type_mapping[dt])
                
                # Refresh data for symbol
                result = refresh_manager.refresh_data(
                    symbol=symbol,
                    data_types=data_types,
                    force=request.force
                )
                
                results[symbol] = {
                    "success": result.total_successful > 0,
                    "total_requested": result.total_requested,
                    "total_successful": result.total_successful,
                    "total_failed": result.total_failed,
                    "results": {
                        dt: {
                            "status": result.results[dt.name].status.value if dt.name in result.results else "skipped",
                            "message": result.results[dt.name].message if dt.name in result.results else "Not requested"
                        }
                        for dt in data_types
                    }
                }
                
                if result.total_successful > 0:
                    successful_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to refresh {symbol}: {e}")
                results[symbol] = {
                    "success": False,
                    "error": str(e)
                }
                failed_count += 1
        
        return RefreshResponse(
            success=successful_count > 0,
            message=f"Refreshed {successful_count}/{len(request.symbols)} symbols successfully",
            results=results
        )
        
    except Exception as e:
        logger.error(f"Failed to refresh data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/recent")
async def get_recent_signals(limit: int = 50):
    """Get recent trading signals"""
    try:
        # Query recent signals from database
        query = """
            SELECT 
                symbol,
                signal,
                confidence_score,
                strategy_name,
                created_at
            FROM indicators_daily 
            WHERE signal IS NOT NULL 
            ORDER BY created_at DESC
            LIMIT %s
        """
        
        results = db.execute_query(query, [limit])
        
        signals = []
        for row in results:
            signals.append({
                "symbol": row["symbol"],
                "signal": row["signal"],
                "confidence": row["confidence_score"],
                "strategy": row["strategy_name"] or "technical",
                "timestamp": row["created_at"].isoformat(),
                "price": None  # Would need to join with price data
            })
        
        return {"signals": signals}
        
    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/screener/results/{screener_id}")
async def get_screener_results(screener_id: str):
    """Get screener results by ID"""
    try:
        # For now, return mock data
        # In a real implementation, this would query a screener_results table
        return {
            "screener_id": screener_id,
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "results": [
                {
                    "symbol": "AAPL",
                    "score": 85,
                    "current_price": 173.50,
                    "rsi": 45.2,
                    "sma_50": 175.20
                }
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get screener results: {e}")
        raise HTTPException(status_code=500, detail=str(e))
