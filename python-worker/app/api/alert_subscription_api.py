"""
Alert Subscription API
REST API for managing alert subscriptions
"""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.services.alert_subscription_service import alert_subscription_service
from app.services.rating_update_service import rating_update_service
from app.observability.logging import get_logger

logger = get_logger("alert_subscription_api")
router = APIRouter(prefix="/api/v1/alert-subscriptions", tags=["alert-subscriptions"])


# Pydantic models for API
class SubscriptionRequest(BaseModel):
    symbol: str = Field(..., description="Stock symbol")
    alert_type: str = Field(..., description="Alert type")
    priority: int = Field(default=2, ge=1, le=5, description="Priority (1=High, 5=Low)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Alert configuration")


class BulkSubscriptionRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of stock symbols")
    alert_types: List[str] = Field(..., description="List of alert types")
    priority: int = Field(default=2, ge=1, le=5, description="Priority")
    config: Dict[str, Any] = Field(default_factory=dict, description="Alert configuration")


class SubscriptionResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


@router.get("/types", response_model=Dict[str, Any])
async def get_alert_types():
    """Get all available alert types"""
    try:
        alert_types = await alert_subscription_service.get_alert_types()
        return {
            "success": True,
            "alert_types": [
                {
                    "alert_type": at.alert_type,
                    "name": at.name,
                    "description": at.description,
                    "default_config": at.default_config
                }
                for at in alert_types
            ]
        }
    except Exception as e:
        logger.error(f"❌ Error getting alert types: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions", response_model=Dict[str, Any])
async def get_subscriptions(
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    symbol: Optional[str] = Query(None, description="Filter by symbol")
):
    """Get active alert subscriptions"""
    try:
        subscriptions = await alert_subscription_service.get_active_subscriptions(alert_type)
        
        # Filter by symbol if provided
        if symbol:
            subscriptions = [sub for sub in subscriptions if sub.symbol == symbol.upper()]
        
        return {
            "success": True,
            "subscriptions": [
                {
                    "symbol": sub.symbol,
                    "alert_type": sub.alert_type,
                    "enabled": sub.enabled,
                    "priority": sub.priority,
                    "config": sub.config,
                    "created_at": sub.created_at,
                    "updated_at": sub.updated_at
                }
                for sub in subscriptions
            ],
            "total": len(subscriptions)
        }
    except Exception as e:
        logger.error(f"❌ Error getting subscriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscribe", response_model=SubscriptionResponse)
async def subscribe_symbol(request: SubscriptionRequest):
    """Subscribe a symbol to an alert type"""
    try:
        success = await alert_subscription_service.subscribe_symbol(
            symbol=request.symbol.upper(),
            alert_type=request.alert_type,
            priority=request.priority,
            config=request.config
        )
        
        if success:
            return SubscriptionResponse(
                success=True,
                message=f"Successfully subscribed {request.symbol} to {request.alert_type} alerts"
            )
        else:
            return SubscriptionResponse(
                success=False,
                message=f"Failed to subscribe {request.symbol} to {request.alert_type} alerts"
            )
            
    except Exception as e:
        logger.error(f"❌ Error subscribing symbol: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/unsubscribe/{symbol}/{alert_type}", response_model=SubscriptionResponse)
async def unsubscribe_symbol(symbol: str, alert_type: str):
    """Unsubscribe a symbol from an alert type"""
    try:
        success = await alert_subscription_service.unsubscribe_symbol(
            symbol=symbol.upper(),
            alert_type=alert_type
        )
        
        if success:
            return SubscriptionResponse(
                success=True,
                message=f"Successfully unsubscribed {symbol} from {alert_type} alerts"
            )
        else:
            return SubscriptionResponse(
                success=False,
                message=f"No active subscription found for {symbol} to {alert_type}"
            )
            
    except Exception as e:
        logger.error(f"❌ Error unsubscribing symbol: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-subscribe", response_model=Dict[str, Any])
async def bulk_subscribe(request: BulkSubscriptionRequest):
    """Bulk subscribe multiple symbols to multiple alert types"""
    try:
        results = await alert_subscription_service.bulk_subscribe(
            symbols=[s.upper() for s in request.symbols],
            alert_types=request.alert_types,
            priority=request.priority,
            config=request.config
        )
        
        return {
            "success": True,
            "message": f"Bulk subscription completed",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Error in bulk subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=Dict[str, Any])
async def get_subscription_summary():
    """Get subscription summary statistics"""
    try:
        summary = await alert_subscription_service.get_subscription_summary()
        return {
            "success": True,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting subscription summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{alert_type}", response_model=Dict[str, Any])
async def get_symbols_for_alert_type(alert_type: str):
    """Get symbols subscribed to a specific alert type"""
    try:
        symbols = await alert_subscription_service.get_symbols_for_alert_type(alert_type)
        return {
            "success": True,
            "alert_type": alert_type,
            "symbols": sorted(list(symbols)),
            "total": len(symbols)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting symbols for alert type: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Rating update endpoints
@router.post("/rating-updates/process", response_model=Dict[str, Any])
async def process_rating_updates(symbols: Optional[List[str]] = Body(None)):
    """Process rating updates for subscribed symbols"""
    try:
        results = await rating_update_service.process_rating_updates(symbols)
        
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        return {
            "success": True,
            "message": f"Processed {len(results)} symbols",
            "results": {
                "total": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "successful_updates": [
                    {
                        "symbol": r.symbol,
                        "old_rating": r.old_rating,
                        "new_rating": r.new_rating,
                        "old_price_target": r.old_price_target,
                        "new_price_target": r.new_price_target,
                        "consensus_score": r.consensus_score
                    }
                    for r in successful
                ],
                "failed_updates": [
                    {
                        "symbol": r.symbol,
                        "error": r.error_message
                    }
                    for r in failed
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing rating updates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rating-updates/statistics", response_model=Dict[str, Any])
async def get_rating_update_statistics(days: int = Query(default=7, ge=1, le=30)):
    """Get rating update statistics"""
    try:
        stats = await rating_update_service.get_update_statistics(days)
        return {
            "success": True,
            "statistics": stats,
            "days": days
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting rating update statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Quick setup endpoints for common use cases
@router.post("/setup/top-stocks", response_model=SubscriptionResponse)
async def setup_top_stocks():
    """Subscribe top S&P 500 stocks to all alert types"""
    try:
        # Get top 100 stocks by market cap (this would be a separate query)
        top_symbols = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM", 
            "JNJ", "V", "PG", "UNH", "HD", "MA", "PYPL", "DIS", "NFLX", "ADBE", "CRM"
        ]
        
        alert_types = ["rating_updates", "price_target_updates", "earnings_updates"]
        
        results = await alert_subscription_service.bulk_subscribe(
            symbols=top_symbols,
            alert_types=alert_types,
            priority=1  # High priority for top stocks
        )
        
        return SubscriptionResponse(
            success=True,
            message=f"Setup complete for {len(top_symbols)} top stocks",
            data=results
        )
        
    except Exception as e:
        logger.error(f"❌ Error setting up top stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup/watchlist", response_model=SubscriptionResponse)
async def setup_watchlist(symbols: List[str] = Body(...)):
    """Subscribe custom watchlist to rating and price target alerts"""
    try:
        alert_types = ["rating_updates", "price_target_updates"]
        
        results = await alert_subscription_service.bulk_subscribe(
            symbols=[s.upper() for s in symbols],
            alert_types=alert_types,
            priority=2  # Medium priority for watchlist
        )
        
        return SubscriptionResponse(
            success=True,
            message=f"Watchlist setup complete for {len(symbols)} symbols",
            data=results
        )
        
    except Exception as e:
        logger.error(f"❌ Error setting up watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))
