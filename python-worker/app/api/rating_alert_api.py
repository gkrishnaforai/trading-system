"""
Rating Alert API - Complete rating and alert management API
REST API for rating updates, price targets, and alert management
"""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Body, Path
from pydantic import BaseModel, Field

from app.services.rating_service import rating_service
from app.services.alert_management_service import alert_management_service
from app.observability.logging import get_logger

logger = get_logger("rating_alert_api")
router = APIRouter(prefix="/rating-alerts", tags=["rating-alerts"])


# Pydantic models for API requests/responses
class RatingAlertRequest(BaseModel):
    stock_symbol: str = Field(..., description="Stock symbol")
    alert_type: str = Field(..., description="Alert type")
    name: str = Field(..., description="Alert name")
    config: Dict[str, Any] = Field(default_factory=dict, description="Alert configuration")
    notification_channels: List[str] = Field(default=["email"], description="Notification channels")


class RatingAlertUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Alert name")
    enabled: Optional[bool] = Field(None, description="Alert enabled status")
    config: Optional[Dict[str, Any]] = Field(None, description="Alert configuration")
    notification_channels: Optional[List[str]] = Field(None, description="Notification channels")


class RatingSubscriptionRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of stock symbols")
    subscription_type: str = Field(default="rating_updates", description="Subscription type")
    priority: int = Field(default=2, ge=1, le=5, description="Priority")
    config: Dict[str, Any] = Field(default_factory=dict, description="Subscription configuration")


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


# Rating Management Endpoints
@router.get("/ratings/{symbol}", response_model=Dict[str, Any])
async def get_rating_data(symbol: str = Path(..., description="Stock symbol")):
    """Get current rating data and history for a symbol"""
    try:
        summary = await rating_service.get_rating_summary(symbol.upper())
        
        if not summary:
            raise HTTPException(status_code=404, detail=f"No rating data found for {symbol}")
        
        return {
            "success": True,
            "symbol": symbol.upper(),
            "data": summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting rating data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ratings/update/{symbol}", response_model=Dict[str, Any])
async def update_rating_data(symbol: str = Path(..., description="Stock symbol")):
    """Update rating data for a specific symbol"""
    try:
        change = await rating_service.update_symbol_ratings(symbol.upper())
        
        if change is None:
            return {
                "success": True,
                "message": f"No updates needed for {symbol}",
                "data": {"changes": False}
            }
        
        return {
            "success": True,
            "message": f"Updated rating data for {symbol}",
            "data": {
                "changes": True,
                "change_type": change.change_type,
                "old_rating": change.old_rating,
                "new_rating": change.new_rating,
                "old_price_target": change.old_price_target,
                "new_price_target": change.new_price_target,
                "rating_score": change.rating_score
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error updating rating data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ratings/batch-update", response_model=Dict[str, Any])
async def batch_update_ratings(symbols: List[str] = Body(..., description="List of stock symbols")):
    """Update rating data for multiple symbols"""
    try:
        if not symbols:
            raise HTTPException(status_code=400, detail="No symbols provided")
        
        symbols = [s.upper() for s in symbols]
        changes = await rating_service.batch_update_ratings(symbols)
        
        return {
            "success": True,
            "message": f"Batch update complete for {len(symbols)} symbols",
            "data": {
                "total_symbols": len(symbols),
                "total_changes": len(changes),
                "changes": [
                    {
                        "symbol": change.symbol,
                        "change_type": change.change_type,
                        "old_rating": change.old_rating,
                        "new_rating": change.new_rating,
                        "old_price_target": change.old_price_target,
                        "new_price_target": change.new_price_target,
                        "rating_score": change.rating_score
                    }
                    for change in changes
                ]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in batch rating update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ratings/statistics", response_model=Dict[str, Any])
async def get_rating_statistics(days: int = Query(default=7, ge=1, le=30, description="Number of days")):
    """Get rating update statistics"""
    try:
        stats = await rating_service.get_statistics(days)
        
        return {
            "success": True,
            "statistics": stats,
            "days": days
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting rating statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alert Management Endpoints
@router.post("/alerts", response_model=ApiResponse)
async def create_rating_alert(request: RatingAlertRequest, user_id: str = Query(..., description="User ID")):
    """Create a new rating alert"""
    try:
        alert_id = alert_management_service.create_rating_alert(
            user_id=user_id,
            stock_symbol=request.stock_symbol.upper(),
            alert_type=request.alert_type,
            name=request.name,
            config=request.config,
            notification_channels=request.notification_channels
        )
        
        if alert_id:
            return ApiResponse(
                success=True,
                message=f"Alert created successfully for {request.stock_symbol}",
                data={"alert_id": alert_id}
            )
        else:
            return ApiResponse(
                success=False,
                message=f"Failed to create alert for {request.stock_symbol}"
            )
            
    except Exception as e:
        logger.error(f"❌ Error creating alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts", response_model=Dict[str, Any])
async def get_user_alerts(
    user_id: str = Query(..., description="User ID"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type")
):
    """Get all alerts for a user"""
    try:
        alerts = alert_management_service.get_user_alerts(user_id, alert_type)
        
        return {
            "success": True,
            "alerts": [
                {
                    "alert_id": alert.alert_id,
                    "stock_symbol": alert.stock_symbol,
                    "alert_type": alert.alert_type,
                    "name": alert.name,
                    "enabled": alert.enabled,
                    "config": alert.config,
                    "notification_channels": alert.notification_channels,
                    "created_at": alert.created_at,
                    "updated_at": alert.updated_at
                }
                for alert in alerts
            ],
            "total": len(alerts)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting user alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/add-symbols", response_model=Dict[str, Any])
async def add_symbols_to_alert(
    alert_id: str = Path(..., description="Alert ID"),
    user_id: str = Query(..., description="User ID"),
    symbols: List[str] = Body(..., description="List of stock symbols to add")
):
    """Add multiple stock symbols to an existing alert"""
    try:
        results = []
        
        for symbol in symbols:
            # Create a new alert for each symbol with the same configuration
            alert_request = RatingAlertRequest(
                stock_symbol=symbol.upper(),
                alert_type="",  # Will be set from existing alert
                name="",  # Will be set from existing alert
                config={},  # Will be set from existing alert
                notification_channels=[]  # Will be set from existing alert
            )
            
            success = alert_management_service.create_alert_for_symbol(
                alert_id, user_id, alert_request
            )
            
            results.append({
                "symbol": symbol.upper(),
                "success": success,
                "message": f"Alert created for {symbol}" if success else f"Failed to create alert for {symbol}"
            })
        
        successful_count = sum(1 for r in results if r["success"])
        
        return {
            "success": True,
            "message": f"Added {successful_count}/{len(symbols)} symbols to alert",
            "results": results,
            "total_requested": len(symbols),
            "total_successful": successful_count
        }
        
    except Exception as e:
        logger.error(f"❌ Error adding symbols to alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/{alert_id}/symbols/{symbol}", response_model=Dict[str, Any])
async def remove_symbol_from_alert(
    alert_id: str = Path(..., description="Alert ID"),
    symbol: str = Path(..., description="Stock symbol to remove"),
    user_id: str = Query(..., description="User ID")
):
    """Remove a stock symbol from an alert"""
    try:
        success = alert_management_service.delete_alert_for_symbol(alert_id, user_id, symbol.upper())
        
        if success:
            return {
                "success": True,
                "message": f"Removed {symbol.upper()} from alert"
            }
        else:
            return {
                "success": False,
                "message": f"Failed to remove {symbol.upper()} from alert"
            }
        
    except Exception as e:
        logger.error(f"❌ Error removing symbol {symbol} from alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/{alert_id}/symbols", response_model=Dict[str, Any])
async def get_alert_symbols(
    alert_id: str = Path(..., description="Alert ID"),
    user_id: str = Query(..., description="User ID")
):
    """Get all stock symbols for an alert"""
    try:
        symbols = alert_management_service.get_alert_symbols(alert_id, user_id)
        
        return {
            "success": True,
            "alert_id": alert_id,
            "symbols": symbols,
            "total": len(symbols)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting symbols for alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/{alert_id}", response_model=Dict[str, Any])
async def get_alert(alert_id: str = Path(..., description="Alert ID"), user_id: str = Query(..., description="User ID")):
    """Get a specific alert"""
    try:
        alert = alert_management_service.get_alert(alert_id, user_id)
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {
            "success": True,
            "alert": {
                "alert_id": alert.alert_id,
                "stock_symbol": alert.stock_symbol,
                "alert_type": alert.alert_type,
                "name": alert.name,
                "enabled": alert.enabled,
                "config": alert.config,
                "notification_channels": alert.notification_channels,
                "created_at": alert.created_at,
                "updated_at": alert.updated_at
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/alerts/{alert_id}", response_model=ApiResponse)
async def update_alert(
    alert_id: str = Path(..., description="Alert ID"),
    request: RatingAlertUpdateRequest = Body(...),
    user_id: str = Query(..., description="User ID")
):
    """Update an existing alert"""
    try:
        success = await alert_management_service.update_alert(
            alert_id=alert_id,
            user_id=user_id,
            name=request.name,
            enabled=request.enabled,
            config=request.config,
            notification_channels=request.notification_channels
        )
        
        if success:
            return ApiResponse(
                success=True,
                message=f"Alert {alert_id} updated successfully"
            )
        else:
            return ApiResponse(
                success=False,
                message=f"Failed to update alert {alert_id}"
            )
            
    except Exception as e:
        logger.error(f"❌ Error updating alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/{alert_id}", response_model=ApiResponse)
async def delete_alert(alert_id: str = Path(..., description="Alert ID"), user_id: str = Query(..., description="User ID")):
    """Delete an alert"""
    try:
        success = await alert_management_service.delete_alert(alert_id, user_id)
        
        if success:
            return ApiResponse(
                success=True,
                message=f"Alert {alert_id} deleted successfully"
            )
        else:
            return ApiResponse(
                success=False,
                message=f"Failed to delete alert {alert_id}"
            )
            
    except Exception as e:
        logger.error(f"❌ Error deleting alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Subscription Management Endpoints
@router.post("/subscriptions", response_model=Dict[str, Any])
async def create_rating_subscription(request: RatingSubscriptionRequest, user_id: str = Query(..., description="User ID")):
    """Subscribe to rating updates for multiple symbols"""
    try:
        results = await alert_management_service.subscribe_to_rating_updates(
            user_id=user_id,
            symbols=[s.upper() for s in request.symbols],
            subscription_type=request.subscription_type,
            priority=request.priority,
            config=request.config
        )
        
        return {
            "success": True,
            "message": f"Subscription complete for {len(request.symbols)} symbols",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions", response_model=Dict[str, Any])
async def get_user_subscriptions(
    user_id: str = Query(..., description="User ID"),
    subscription_type: Optional[str] = Query(None, description="Filter by subscription type")
):
    """Get user's rating subscriptions"""
    try:
        subscriptions = await alert_management_service.get_user_subscriptions(user_id, subscription_type)
        
        return {
            "success": True,
            "subscriptions": [
                {
                    "symbol": sub.symbol,
                    "subscription_type": sub.subscription_type,
                    "enabled": sub.enabled,
                    "priority": sub.priority,
                    "config": sub.config,
                    "created_at": sub.created_at
                }
                for sub in subscriptions
            ],
            "total": len(subscriptions)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting subscriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=Dict[str, Any])
async def get_alert_summary(user_id: str = Query(..., description="User ID")):
    """Get alert and subscription summary for a user"""
    try:
        summary = await alert_management_service.get_alert_summary(user_id)
        
        return {
            "success": True,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting alert summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Quick Setup Endpoints
@router.post("/setup/top-stocks", response_model=ApiResponse)
async def setup_top_stocks_alerts(user_id: str = Query(..., description="User ID")):
    """Setup alerts for top stocks"""
    try:
        top_symbols = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM",
            "JNJ", "V", "PG", "UNH", "HD", "MA", "PYPL", "DIS", "NFLX", "ADBE", "CRM"
        ]
        
        # Create rating change alerts for top stocks
        alert_count = 0
        for symbol in top_symbols:
            alert_id = await alert_management_service.create_rating_alert(
                user_id=user_id,
                stock_symbol=symbol,
                alert_type="rating_change",
                name=f"{symbol} Rating Changes",
                config={"min_consensus_change": 0.3},
                notification_channels=["email"]
            )
            
            if alert_id:
                alert_count += 1
        
        # Subscribe to rating updates
        subscription_results = await alert_management_service.subscribe_to_rating_updates(
            user_id=user_id,
            symbols=top_symbols,
            subscription_type="rating_updates",
            priority=1
        )
        
        return ApiResponse(
            success=True,
            message=f"Setup complete for top stocks",
            data={
                "alerts_created": alert_count,
                "subscriptions": subscription_results
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Error setting up top stocks alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup/watchlist", response_model=ApiResponse)
async def setup_watchlist_alerts(
    symbols: List[str] = Body(..., description="List of stock symbols"),
    user_id: str = Query(..., description="User ID")
):
    """Setup alerts for custom watchlist"""
    try:
        if not symbols:
            raise HTTPException(status_code=400, detail="No symbols provided")
        
        symbols = [s.upper() for s in symbols]
        
        # Create alerts for each symbol
        alert_count = 0
        for symbol in symbols:
            alert_id = await alert_management_service.create_rating_alert(
                user_id=user_id,
                stock_symbol=symbol,
                alert_type="rating_change",
                name=f"{symbol} Rating Changes",
                config={"min_consensus_change": 0.3},
                notification_channels=["email"]
            )
            
            if alert_id:
                alert_count += 1
        
        # Subscribe to updates
        subscription_results = await alert_management_service.subscribe_to_rating_updates(
            user_id=user_id,
            symbols=symbols,
            subscription_type="rating_updates",
            priority=2
        )
        
        return ApiResponse(
            success=True,
            message=f"Watchlist setup complete for {len(symbols)} symbols",
            data={
                "alerts_created": alert_count,
                "subscriptions": subscription_results
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error setting up watchlist alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alert Types Information
@router.get("/alert-types", response_model=Dict[str, Any])
async def get_alert_types():
    """Get available alert types and their configurations"""
    try:
        alert_types = {
            "rating_change": {
                "name": "Rating Change",
                "description": "Alert when analyst ratings change",
                "config_schema": {
                    "min_consensus_change": {"type": "number", "default": 0.3},
                    "tier_1_firms_only": {"type": "boolean", "default": False},
                    "include_upgrades": {"type": "boolean", "default": True},
                    "include_downgrades": {"type": "boolean", "default": True},
                    "notification_delay_minutes": {"type": "integer", "default": 5}
                }
            },
            "price_target_change": {
                "name": "Price Target Change",
                "description": "Alert when consensus price targets change",
                "config_schema": {
                    "min_price_change_percent": {"type": "number", "default": 5.0},
                    "min_analyst_count": {"type": "integer", "default": 3},
                    "include_increases": {"type": "boolean", "default": True},
                    "include_decreases": {"type": "boolean", "default": True},
                    "notification_delay_minutes": {"type": "integer", "default": 10}
                }
            },
            "consensus_alert": {
                "name": "Consensus Alert",
                "description": "Alert when consensus reaches specific levels",
                "config_schema": {
                    "target_consensus": {"type": "string", "enum": ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]},
                    "min_analyst_count": {"type": "integer", "default": 5},
                    "direction": {"type": "string", "enum": ["above", "below", "exactly"], "default": "above"},
                    "notification_delay_minutes": {"type": "integer", "default": 15}
                }
            },
            "earnings_alert": {
                "name": "Earnings Alert",
                "description": "Alert for earnings announcements and surprises",
                "config_schema": {
                    "include_pre_announcements": {"type": "boolean", "default": True},
                    "include_surprises_only": {"type": "boolean", "default": False},
                    "min_surprise_percent": {"type": "number", "default": 5.0},
                    "days_before_earnings": {"type": "integer", "default": 1},
                    "notification_delay_minutes": {"type": "integer", "default": 15}
                }
            }
        }
        
        return {
            "success": True,
            "alert_types": alert_types
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting alert types: {e}")
        raise HTTPException(status_code=500, detail=str(e))
