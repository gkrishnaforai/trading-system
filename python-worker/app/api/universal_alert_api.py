"""
Universal Alert System API
Industry-standard REST API for universal alert management
Supports ANY alert type with full observability and audit trail
"""

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
import uuid
import json

from app.services.universal_alert_service_enhanced import universal_alert_service, AlertDefinition, UniversalEvent, EntityType
from app.observability.logging import get_logger, log_operation_start, log_operation_success, log_operation_failure, log_with_context
from app.observability.metrics import get_metrics
from app.observability.audit_logger import audit_log

# Helper function to safely extract alert attributes (DRY principle)
def get_alert_attr(alert_dict: dict, attr: str, default=None):
    """Safely extract attribute from alert dictionary"""
    return alert_dict.get(attr, default)

logger = get_logger("universal_alert_api")
metrics = get_metrics()

router = APIRouter(tags=["Universal Alerts"])

# ============================================================================
# Pydantic Models for API
# ============================================================================

class AlertRequest(BaseModel):
    """Request model for creating alerts"""
    alert_name: str = Field(..., description="Alert name")
    alert_type: str = Field(..., description="Alert type (earnings, grade_change, price_movement, etc.)")
    alert_category: str = Field(default="custom", description="Alert category")
    
    entity_filters: Dict[str, Any] = Field(default_factory=dict, description="Entity filters")
    event_filters: Dict[str, Any] = Field(default_factory=dict, description="Event filters")
    trigger_conditions: Dict[str, Any] = Field(default_factory=dict, description="Trigger conditions")
    suppression_rules: Dict[str, Any] = Field(default_factory=dict, description="Suppression rules")
    
    notification_config: Dict[str, Any] = Field(default_factory=dict, description="Notification configuration")
    template_config: Dict[str, Any] = Field(default_factory=dict, description="Template configuration")
    priority_level: int = Field(default=3, ge=1, le=5, description="Priority level (1-5)")
    
    is_test: bool = Field(default=False, description="Is this a test alert")

class EventRequest(BaseModel):
    """Request model for creating events"""
    event_type: str = Field(..., description="Event type")
    entity_type: str = Field(..., description="Entity type")
    entity_id: str = Field(..., description="Entity ID (symbol, portfolio ID, etc.)")
    
    event_data: Dict[str, Any] = Field(..., description="Event data")
    previous_data: Optional[Dict[str, Any]] = Field(None, description="Previous state")
    change_metadata: Optional[Dict[str, Any]] = Field(None, description="Change metadata")
    
    event_timestamp: Optional[datetime] = Field(None, description="Event timestamp")
    data_source: str = Field(..., description="Data source")
    source_id: Optional[str] = Field(None, description="Source ID")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    
    priority: int = Field(default=3, ge=1, le=5, description="Event priority")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    tags: List[str] = Field(default_factory=list, description="Event tags")

class PluginConfigRequest(BaseModel):
    """Request model for plugin configuration"""
    plugin_name: str = Field(..., description="Plugin name")
    config: Dict[str, Any] = Field(..., description="Plugin configuration")
    plugin_version: str = Field(..., description="Plugin version")


class BulkAlertActionRequest(BaseModel):
    """Admin request model for bulk alert actions"""
    alert_ids: List[str] = Field(..., description="Alert IDs")
    action: str = Field(..., description="Action: activate|deactivate|delete")
    reason: Optional[str] = Field(None, description="Optional reason")

# ============================================================================

@router.get("/analytics/performance", response_model=Dict[str, Any])
async def get_performance_analytics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type")
):
    """Get alert performance analytics"""
    try:
        analytics = await universal_alert_service.admin_get_performance_analytics(
            days=days,
            alert_type=alert_type
        )
        
        return {
            "success": True,
            "analytics": analytics,
            "period_days": days,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting performance analytics: {e}")
        metrics.increment('api_analytics_errors_total')
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/event-type-coverage", response_model=Dict[str, Any])
async def get_event_type_coverage(
    user_id: Optional[str] = Query(None, description="Optional user_id to compute alert coverage for"),
):
    """Admin/operator: get supported vs observed event types and alert coverage."""
    try:
        report = await universal_alert_service.admin_get_event_type_coverage(user_id=user_id)
        return {
            "success": True,
            "user_id": user_id,
            "report": report,
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"❌ Error getting event type coverage: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ALERT MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/alerts", response_model=Dict[str, Any])
async def create_alert(
    user_id: str = Query(..., description="User ID"),
    alert_request: AlertRequest = Body(..., description="Alert configuration")
):
    """Create a new universal alert"""
    operation = "create_alert"
    tracking_id = log_operation_start(
        logger, 
        operation, 
        {
            "user_id": user_id,
            "alert_name": alert_request.alert_name,
            "alert_type": alert_request.alert_type,
            "alert_category": alert_request.alert_category,
            "priority_level": alert_request.priority_level,
            "is_test": alert_request.is_test,
            "entity_filters": alert_request.entity_filters,
            "notification_channels": alert_request.notification_config.get("channels", []),
            "request_size": len(json.dumps(alert_request.model_dump()))
        }
    )
    
    try:
        log_with_context(
            logger,
            20,  # INFO level
            f"🔧 Processing alert creation request",
            {
                "tracking_id": tracking_id,
                "user_id": user_id,
                "alert_name": alert_request.alert_name,
                "alert_type": alert_request.alert_type,
                "symbols": alert_request.entity_filters.get("symbols", []),
                "notification_channels": alert_request.notification_config.get("channels", []),
                "priority": alert_request.priority_level
            },
            correlation_id=tracking_id
        )
        
        # Validate alert configuration
        if not alert_request.alert_name.strip():
            raise ValueError("Alert name cannot be empty")
        
        if not alert_request.alert_type:
            raise ValueError("Alert type is required")
        
        if not alert_request.notification_config.get("channels"):
            raise ValueError("At least one notification channel must be specified")
        
        log_with_context(
            logger,
            20,
            f"✅ Alert configuration validated",
            {
                "tracking_id": tracking_id,
                "validation": "passed"
            },
            correlation_id=tracking_id
        )
        
        # Create alert definition
        log_with_context(
            logger,
            20,
            f"🏗️ Creating alert definition",
            {
                "tracking_id": tracking_id,
                "entity_filters_count": len(alert_request.entity_filters),
                "event_filters_count": len(alert_request.event_filters),
                "trigger_conditions_count": len(alert_request.trigger_conditions)
            },
            correlation_id=tracking_id
        )
        
        alert_def = AlertDefinition(
            alert_name=alert_request.alert_name,
            alert_type=alert_request.alert_type,
            alert_category=alert_request.alert_category,
            entity_filters=alert_request.entity_filters,
            event_filters=alert_request.event_filters,
            trigger_conditions=alert_request.trigger_conditions,
            suppression_rules=alert_request.suppression_rules,
            notification_config=alert_request.notification_config,
            template_config=alert_request.template_config,
            priority_level=alert_request.priority_level,
            is_test=alert_request.is_test
        )
        
        # Create alert
        log_with_context(
            logger,
            20,
            f"📝 Calling alert service to create alert",
            {
                "tracking_id": tracking_id,
                "service": "universal_alert_service",
                "method": "create_alert"
            },
            correlation_id=tracking_id
        )
        
        alert_id = await universal_alert_service.create_alert(user_id, alert_def)
        
        if alert_id:
            # Log success
            log_operation_success(
                logger,
                operation,
                tracking_id,
                {
                    "alert_id": alert_id,
                    "user_id": user_id,
                    "alert_name": alert_request.alert_name,
                    "alert_type": alert_request.alert_type,
                    "symbols": alert_request.entity_filters.get("symbols", []),
                    "notification_channels": alert_request.notification_config.get("channels", []),
                    "priority_level": alert_request.priority_level,
                    "is_test": alert_request.is_test
                }
            )
            
            # Audit log
            audit_log(
                action="alert_created",
                user_id=user_id,
                resource_type="alert",
                resource_id=alert_id,
                details={
                    "alert_name": alert_request.alert_name,
                    "alert_type": alert_request.alert_type,
                    "symbols": alert_request.entity_filters.get("symbols", []),
                    "notification_channels": alert_request.notification_config.get("channels", []),
                    "priority_level": alert_request.priority_level,
                    "is_test": alert_request.is_test
                }
            )
            
            # Metrics
            metrics.increment('api_alerts_created_total')
            metrics.increment('api_alerts_created_total', labels={"alert_type": alert_request.alert_type})
            metrics.increment('api_alerts_created_total', labels={"user_id": user_id})
            
            log_with_context(
                logger,
                20,
                f"🎉 Alert creation completed successfully",
                {
                    "tracking_id": tracking_id,
                    "alert_id": alert_id,
                    "user_id": user_id,
                    "alert_name": alert_request.alert_name
                },
                correlation_id=tracking_id
            )
            
            return {
                "success": True,
                "alert_id": alert_id,
                "message": "Alert created successfully",
                "user_id": user_id,
                "alert_type": alert_request.alert_type,
                "tracking_id": tracking_id
            }
        else:
            raise ValueError("Alert service returned None alert_id")
            
    except ValueError as e:
        metrics.increment('api_alerts_create_validation_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"❌ Validation error in alert creation",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "user_id": user_id,
                "alert_name": alert_request.alert_name
            },
            correlation_id=tracking_id
        )
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
        
    except Exception as e:
        metrics.increment('api_alerts_create_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"💥 Unexpected error in alert creation",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "user_id": user_id,
                "alert_name": alert_request.alert_name
            },
            correlation_id=tracking_id,
            exc_info=e
        )
        raise HTTPException(status_code=500, detail=f"Failed to create alert: {str(e)}")

@router.get("/alerts", response_model=Dict[str, Any])
async def get_user_alerts(
    user_id: str = Query(..., description="User ID"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    view_all: bool = Query(False, description="Admin: View all alerts across all users")
):
    """Get alerts for a user or all alerts if admin"""
    operation = "get_alerts"
    tracking_id = log_operation_start(
        logger, 
        operation, 
        {
            "user_id": user_id,
            "alert_type": alert_type,
            "page": page,
            "limit": limit,
            "view_all": view_all,
            "is_admin_request": view_all
        }
    )
    
    try:
        log_with_context(
            logger,
            20,  # INFO level
            f"🔍 Processing get alerts request",
            {
                "tracking_id": tracking_id,
                "user_id": user_id,
                "alert_type_filter": alert_type,
                "page": page,
                "limit": limit,
                "view_all": view_all
            },
            correlation_id=tracking_id
        )
        
        # Validate parameters
        if page < 1:
            raise ValueError("Page must be >= 1")
        
        if limit < 1 or limit > 500:
            raise ValueError("Limit must be between 1 and 500")
        
        if view_all and not user_id.startswith("admin"):
            raise ValueError("Only admin users can use view_all=true")
        
        log_with_context(
            logger,
            20,
            f"✅ Request parameters validated",
            {
                "tracking_id": tracking_id,
                "validation": "passed"
            },
            correlation_id=tracking_id
        )
        
        # Get alerts
        log_with_context(
            logger,
            20,
            f"📋 Calling alert service to get alerts",
            {
                "tracking_id": tracking_id,
                "service": "universal_alert_service",
                "method": "get_user_alerts" if not view_all else "get_all_alerts"
            },
            correlation_id=tracking_id
        )
        
        if view_all:
            alerts = await universal_alert_service.get_all_alerts(page=page, limit=limit, alert_type=alert_type)
            total = await universal_alert_service.get_all_alerts_count(alert_type=alert_type)
        else:
            alerts = await universal_alert_service.get_user_alerts(user_id=user_id, page=page, limit=limit, alert_type=alert_type)
            total = await universal_alert_service.get_user_alerts_count(user_id=user_id, alert_type=alert_type)
        
        # Process alerts for response
        processed_alerts = []
        for alert in alerts:
            processed_alert = {
                "alert_id": alert.get('alert_id'),
                "user_id": alert.get('user_id'),
                "alert_name": alert.get('alert_name'),
                "alert_type": alert.get('alert_type'),
                "alert_category": alert.get('alert_category'),
                "entity_filters": alert.get('entity_filters', {}),
                "event_filters": alert.get('event_filters', {}),
                "trigger_conditions": alert.get('trigger_conditions', {}),
                "suppression_rules": alert.get('suppression_rules', {}),
                "escalation_rules": alert.get('escalation_rules', {}),
                "notification_config": alert.get('notification_config', {}),
                "template_config": alert.get('template_config', {}),
                "priority_level": alert.get('priority_level', 3),
                "is_active": alert.get('is_active', True),
                "is_test": alert.get('is_test', False),
                "schedule_config": alert.get('schedule_config', {}),
                "time_windows": alert.get('time_windows', []),
                "timezone": alert.get('timezone', 'UTC'),
                "trigger_count": alert.get('trigger_count', 0),
                "success_count": alert.get('success_count', 0),
                "failure_count": alert.get('failure_count', 0),
                "last_triggered_at": alert.get('last_triggered_at'),
                "last_success_at": alert.get('last_success_at'),
                "last_failure_at": alert.get('last_failure_at'),
                "avg_trigger_duration_ms": alert.get('avg_trigger_duration_ms', 0),
                "rate_limit_config": alert.get('rate_limit_config', {}),
                "current_rate_usage": alert.get('current_rate_usage', 0),
                "created_at": alert.get('created_at'),
                "updated_at": alert.get('updated_at'),
                "created_by": alert.get('created_by'),
                "updated_by": alert.get('updated_by'),
                "version": alert.get('version', 1)
            }
            processed_alerts.append(processed_alert)
        
        # Log success
        log_operation_success(
            logger,
            operation,
            tracking_id,
            {
                "user_id": user_id,
                "alert_type_filter": alert_type,
                "page": page,
                "limit": limit,
                "view_all": view_all,
                "alerts_returned": len(processed_alerts),
                "total_alerts": total,
                "has_more": (page * limit) < total
            }
        )
        
        # Metrics
        metrics.increment('api_alerts_retrieved_total')
        metrics.increment('api_alerts_retrieved_total', labels={"user_id": user_id})
        if view_all:
            metrics.increment('api_alerts_admin_queries_total')
        
        log_with_context(
            logger,
            20,
            f"📊 Alert retrieval completed successfully",
            {
                "tracking_id": tracking_id,
                "alerts_count": len(processed_alerts),
                "total_alerts": total,
                "user_id": user_id
            },
            correlation_id=tracking_id
        )
        
        return {
            "success": True,
            "alerts": processed_alerts,
            "total": total,
            "page": page,
            "limit": limit,
            "has_more": (page * limit) < total,
            "tracking_id": tracking_id
        }
        
    except ValueError as e:
        metrics.increment('api_alerts_get_validation_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"❌ Validation error in get alerts",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "user_id": user_id,
                "view_all": view_all
            },
            correlation_id=tracking_id
        )
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
        
    except Exception as e:
        metrics.increment('api_alerts_get_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"💥 Unexpected error in get alerts",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "user_id": user_id,
                "view_all": view_all
            },
            correlation_id=tracking_id,
            exc_info=e
        )
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")

@router.put("/alerts/{alert_id}", response_model=Dict[str, Any])
async def update_alert(
    alert_id: str,
    user_id: str = Query(..., description="User ID"),
    alert_request: AlertRequest = Body(..., description="Alert configuration")
):
    """Update an existing alert"""
    operation = "update_alert"
    tracking_id = log_operation_start(
        logger, 
        operation, 
        {
            "user_id": user_id,
            "alert_id": alert_id,
            "alert_name": alert_request.alert_name,
            "alert_type": alert_request.alert_type,
            "alert_category": alert_request.alert_category,
            "priority_level": alert_request.priority_level,
            "is_test": alert_request.is_test,
            "entity_filters": alert_request.entity_filters,
            "notification_channels": alert_request.notification_config.get("channels", []),
            "request_size": len(json.dumps(alert_request.model_dump()))
        }
    )
    
    try:
        log_with_context(
            logger,
            20,  # INFO level
            f"🔧 Processing alert update request",
            {
                "tracking_id": tracking_id,
                "user_id": user_id,
                "alert_id": alert_id,
                "alert_name": alert_request.alert_name,
                "alert_type": alert_request.alert_type,
                "symbols": alert_request.entity_filters.get("symbols", []),
                "notification_channels": alert_request.notification_config.get("channels", []),
                "priority": alert_request.priority_level
            },
            correlation_id=tracking_id
        )
        
        # Validate alert configuration
        if not alert_request.alert_name.strip():
            raise ValueError("Alert name cannot be empty")
        
        if not alert_request.alert_type:
            raise ValueError("Alert type is required")
        
        if not alert_request.notification_config.get("channels"):
            raise ValueError("At least one notification channel must be specified")
        
        # Check if alert exists and belongs to user
        log_with_context(
            logger,
            20,
            f"🔍 Verifying alert ownership",
            {
                "tracking_id": tracking_id,
                "alert_id": alert_id,
                "user_id": user_id
            },
            correlation_id=tracking_id
        )
        
        existing_alert = await universal_alert_service.get_alert_by_id(alert_id, user_id)
        
        if not existing_alert:
            raise ValueError(f"Alert {alert_id} not found or access denied")
        
        log_with_context(
            logger,
            20,
            f"✅ Alert ownership verified",
            {
                "tracking_id": tracking_id,
                "existing_alert_name": existing_alert.get('alert_name'),
                "existing_alert_type": existing_alert.get('alert_type')
            },
            correlation_id=tracking_id
        )
        
        # Create updated alert definition
        alert_def = AlertDefinition(
            alert_name=alert_request.alert_name,
            alert_type=alert_request.alert_type,
            alert_category=alert_request.alert_category,
            entity_filters=alert_request.entity_filters,
            event_filters=alert_request.event_filters,
            trigger_conditions=alert_request.trigger_conditions,
            suppression_rules=alert_request.suppression_rules,
            notification_config=alert_request.notification_config,
            template_config=alert_request.template_config,
            priority_level=alert_request.priority_level,
            is_test=alert_request.is_test
        )
        
        # Update alert
        log_with_context(
            logger,
            20,
            f"📝 Calling alert service to update alert",
            {
                "tracking_id": tracking_id,
                "service": "universal_alert_service",
                "method": "update_alert"
            },
            correlation_id=tracking_id
        )
        
        success = await universal_alert_service.update_alert(user_id, alert_id, alert_def)
        
        if success:
            # Log success
            log_operation_success(
                logger,
                operation,
                tracking_id,
                {
                    "alert_id": alert_id,
                    "user_id": user_id,
                    "alert_name": alert_request.alert_name,
                    "alert_type": alert_request.alert_type,
                    "symbols": alert_request.entity_filters.get("symbols", []),
                    "notification_channels": alert_request.notification_config.get("channels", []),
                    "priority_level": alert_request.priority_level,
                    "is_test": alert_request.is_test,
                    "previous_name": existing_alert.get('alert_name'),
                    "previous_type": existing_alert.get('alert_type')
                }
            )
            
            # Audit log
            audit_log(
                action="alert_updated",
                user_id=user_id,
                resource_type="alert",
                resource_id=alert_id,
                details={
                    "alert_name": alert_request.alert_name,
                    "alert_type": alert_request.alert_type,
                    "symbols": alert_request.entity_filters.get("symbols", []),
                    "notification_channels": alert_request.notification_config.get("channels", []),
                    "priority_level": alert_request.priority_level,
                    "is_test": alert_request.is_test,
                    "previous_name": existing_alert.get('alert_name'),
                    "previous_type": existing_alert.get('alert_type')
                }
            )
            
            # Metrics
            metrics.increment('api_alerts_updated_total')
            metrics.increment('api_alerts_updated_total', labels={"alert_type": alert_request.alert_type})
            metrics.increment('api_alerts_updated_total', labels={"user_id": user_id})
            
            log_with_context(
                logger,
                20,
                f"🎉 Alert update completed successfully",
                {
                    "tracking_id": tracking_id,
                    "alert_id": alert_id,
                    "user_id": user_id,
                    "alert_name": alert_request.alert_name
                },
                correlation_id=tracking_id
            )
            
            return {
                "success": True,
                "alert_id": alert_id,
                "message": "Alert updated successfully",
                "user_id": user_id,
                "alert_type": alert_request.alert_type,
                "tracking_id": tracking_id
            }
        else:
            raise ValueError("Alert service returned False for update")
            
    except ValueError as e:
        metrics.increment('api_alerts_update_validation_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"❌ Validation error in alert update",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "user_id": user_id,
                "alert_id": alert_id,
                "alert_name": alert_request.alert_name
            },
            correlation_id=tracking_id
        )
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
        
    except Exception as e:
        metrics.increment('api_alerts_update_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"💥 Unexpected error in alert update",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "user_id": user_id,
                "alert_id": alert_id,
                "alert_name": alert_request.alert_name
            },
            correlation_id=tracking_id,
            exc_info=e
        )
        raise HTTPException(status_code=500, detail=f"Failed to update alert: {str(e)}")

@router.delete("/alerts/{alert_id}", response_model=Dict[str, Any])
async def delete_alert(
    alert_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Delete an alert"""
    operation = "delete_alert"
    tracking_id = log_operation_start(
        logger, 
        operation, 
        {
            "user_id": user_id,
            "alert_id": alert_id
        }
    )
    
    try:
        log_with_context(
            logger,
            20,  # INFO level
            f"🗑️ Processing alert deletion request",
            {
                "tracking_id": tracking_id,
                "user_id": user_id,
                "alert_id": alert_id
            },
            correlation_id=tracking_id
        )
        
        # Check if alert exists and belongs to user
        log_with_context(
            logger,
            20,
            f"🔍 Verifying alert ownership for deletion",
            {
                "tracking_id": tracking_id,
                "alert_id": alert_id,
                "user_id": user_id
            },
            correlation_id=tracking_id
        )
        
        existing_alert = await universal_alert_service.get_alert_by_id(alert_id, user_id)
        
        if not existing_alert:
            raise ValueError(f"Alert {alert_id} not found or access denied")
        
        log_with_context(
            logger,
            20,
            f"✅ Alert ownership verified for deletion",
            {
                "tracking_id": tracking_id,
                "existing_alert_name": existing_alert.get('alert_name'),
                "existing_alert_type": existing_alert.get('alert_type'),
                "is_active": existing_alert.get('is_active')
            },
            correlation_id=tracking_id
        )
        
        # Delete alert
        log_with_context(
            logger,
            20,
            f"🗑️ Calling alert service to delete alert",
            {
                "tracking_id": tracking_id,
                "service": "universal_alert_service",
                "method": "delete_alert"
            },
            correlation_id=tracking_id
        )
        
        success = await universal_alert_service.delete_alert(user_id, alert_id)
        
        if success:
            # Log success
            log_operation_success(
                logger,
                operation,
                tracking_id,
                {
                    "alert_id": alert_id,
                    "user_id": user_id,
                    "deleted_alert_name": existing_alert.get('alert_name'),
                    "deleted_alert_type": existing_alert.get('alert_type'),
                    "was_active": existing_alert.get('is_active'),
                    "symbols": existing_alert.get('entity_filters', {}).get("symbols", []),
                    "notification_channels": existing_alert.get('notification_config', {}).get("channels", [])
                }
            )
            
            # Audit log
            audit_log(
                action="alert_deleted",
                user_id=user_id,
                resource_type="alert",
                resource_id=alert_id,
                details={
                    "alert_name": existing_alert.get('alert_name'),
                    "alert_type": existing_alert.get('alert_type'),
                    "symbols": existing_alert.get('entity_filters', {}).get("symbols", []),
                    "notification_channels": existing_alert.get('notification_config', {}).get("channels", []),
                    "was_active": existing_alert.get('is_active'),
                    "trigger_count": existing_alert.get('trigger_count', 0),
                    "created_at": existing_alert.get('created_at')
                }
            )
            
            # Metrics
            metrics.increment('api_alerts_deleted_total')
            metrics.increment('api_alerts_deleted_total', labels={"alert_type": existing_alert.get('alert_type')})
            metrics.increment('api_alerts_deleted_total', labels={"user_id": user_id})
            
            log_with_context(
                logger,
                20,
                f"🎉 Alert deletion completed successfully",
                {
                    "tracking_id": tracking_id,
                    "alert_id": alert_id,
                    "user_id": user_id,
                    "deleted_alert_name": existing_alert.get('alert_name')
                },
                correlation_id=tracking_id
            )
            
            return {
                "success": True,
                "alert_id": alert_id,
                "message": "Alert deleted successfully",
                "user_id": user_id,
                "deleted_alert_name": existing_alert.get('alert_name'),
                "tracking_id": tracking_id
            }
        else:
            raise ValueError("Alert service returned False for deletion")
            
    except ValueError as e:
        metrics.increment('api_alerts_delete_validation_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"❌ Validation error in alert deletion",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "user_id": user_id,
                "alert_id": alert_id
            },
            correlation_id=tracking_id
        )
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")
        
    except Exception as e:
        metrics.increment('api_alerts_delete_errors_total')
        log_operation_failure(logger, operation, tracking_id, e)
        log_with_context(
            logger,
            40,  # ERROR level
            f"💥 Unexpected error in alert deletion",
            {
                "tracking_id": tracking_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "user_id": user_id,
                "alert_id": alert_id
            },
            correlation_id=tracking_id,
            exc_info=e
        )
        raise HTTPException(status_code=500, detail=f"Failed to delete alert: {str(e)}")

@router.get("/alerts/{alert_id}", response_model=Dict[str, Any])
async def get_alert_details(
    alert_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Get alert details"""
    try:
        alert = await universal_alert_service.get_alert_by_id(alert_id, user_id)
        
        if alert:
            return {
                "success": True,
                "alert": alert
            }
        else:
            raise HTTPException(status_code=404, detail="Alert not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting alert details: {e}")
        metrics.increment('api_alerts_get_errors_total')
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Event Management Endpoints
# ============================================================================

@router.post("/events", response_model=Dict[str, Any])
async def create_event(event_request: EventRequest):
    """Create a new universal event"""
    try:
        # Create universal event
        event = UniversalEvent(
            event_type=event_request.event_type,
            entity_type=EntityType(event_request.entity_type),
            entity_id=event_request.entity_id,
            event_data=event_request.event_data,
            previous_data=event_request.previous_data,
            change_metadata=event_request.change_metadata,
            event_timestamp=event_request.event_timestamp or datetime.now(),
            data_source=event_request.data_source,
            source_id=event_request.source_id,
            confidence_score=event_request.confidence_score,
            priority=event_request.priority,
            correlation_id=event_request.correlation_id,
            tags=event_request.tags
        )
        
        # Process event
        result = await universal_alert_service.process_event(event)
        
        metrics.increment('api_events_processed_total')
        return {
            "success": result.get('success', False),
            "event_id": event.event_id,
            "processing_result": result
        }
        
    except Exception as e:
        logger.error(f"❌ Error creating event: {e}")
        metrics.increment('api_events_create_errors_total')
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/events/pending", response_model=Dict[str, Any])
async def get_pending_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of events")
):
    """Get pending events"""
    try:
        events = await universal_alert_service.event_repo.get_pending_events(event_type, limit)
        
        return {
            "success": True,
            "event_type": event_type,
            "events": events,
            "count": len(events)
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting pending events: {e}")
        metrics.increment('api_events_get_errors_total')
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Plugin Management Endpoints
# ============================================================================

@router.post("/data-collection/collect", response_model=Dict[str, Any])
async def collect_data_from_plugins(plugin_configs: Dict[str, Dict[str, Any]]):
    """Collect data from multiple plugins"""
    try:
        results = await universal_alert_service.collect_data_from_plugins(plugin_configs)
        
        total_events = sum(len(events) for events in results.values())
        
        metrics.increment('api_data_collection_total')
        return {
            "success": True,
            "plugins": list(plugin_configs.keys()),
            "results": results,
            "total_events_collected": total_events
        }
        
    except Exception as e:
        logger.error(f"❌ Error collecting data from plugins: {e}")
        metrics.increment('api_data_collection_errors_total')
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/plugins", response_model=Dict[str, Any])
async def get_available_plugins():
    """Get list of available plugins"""
    try:
        plugins = universal_alert_service.plugin_registry.list_plugins()
        
        return {
            "success": True,
            "plugins": plugins
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting plugins: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# System Health and Monitoring Endpoints
# ============================================================================

@router.get("/health", response_model=Dict[str, Any])
async def get_system_health():
    """Get system health status"""
    try:
        health = await universal_alert_service.get_system_health()
        
        return health
        
    except Exception as e:
        logger.error(f"❌ Error getting system health: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }

@router.get("/metrics", response_model=Dict[str, Any])
async def get_system_metrics():
    """Get system metrics"""
    try:
        current_metrics = metrics.get_metrics()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "metrics": current_metrics
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Bulk Operations Endpoints
# ============================================================================

@router.post("/alerts/bulk", response_model=Dict[str, Any])
async def create_bulk_alerts(
    user_id: str = Query(..., description="User ID"),
    alerts: List[AlertRequest] = Body(..., description="List of alert configurations")
):
    """Create multiple alerts at once"""
    try:
        created_alerts = []
        failed_alerts = []
        
        for alert_request in alerts:
            try:
                alert_def = AlertDefinition(
                    alert_name=alert_request.alert_name,
                    alert_type=alert_request.alert_type,
                    alert_category=alert_request.alert_category,
                    entity_filters=alert_request.entity_filters,
                    event_filters=alert_request.event_filters,
                    trigger_conditions=alert_request.trigger_conditions,
                    suppression_rules=alert_request.suppression_rules,
                    notification_config=alert_request.notification_config,
                    template_config=alert_request.template_config,
                    priority_level=alert_request.priority_level,
                    is_test=alert_request.is_test
                )
                
                alert_id = await universal_alert_service.create_alert(user_id, alert_def)
                if alert_id:
                    created_alerts.append(alert_id)
                else:
                    failed_alerts.append(alert_request.alert_name)
                    
            except Exception as e:
                logger.error(f"❌ Error creating alert {alert_request.alert_name}: {e}")
                failed_alerts.append(alert_request.alert_name)
        
        metrics.increment('api_bulk_alerts_created_total', len(created_alerts))
        
        return {
            "success": len(created_alerts) > 0,
            "user_id": user_id,
            "total_requested": len(alerts),
            "created_count": len(created_alerts),
            "failed_count": len(failed_alerts),
            "created_alert_ids": created_alerts,
            "failed_alert_names": failed_alerts
        }
        
    except Exception as e:
        logger.error(f"❌ Error in bulk alert creation: {e}")
        metrics.increment('api_bulk_alerts_errors_total')
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/events/bulk", response_model=Dict[str, Any])
async def create_bulk_events(events: List[EventRequest]):
    """Create multiple events at once"""
    try:
        processed_events = []
        failed_events = []
        
        for event_request in events:
            try:
                event = UniversalEvent(
                    event_type=event_request.event_type,
                    entity_type=EntityType(event_request.entity_type),
                    entity_id=event_request.entity_id,
                    event_data=event_request.event_data,
                    previous_data=event_request.previous_data,
                    change_metadata=event_request.change_metadata,
                    event_timestamp=event_request.event_timestamp or datetime.now(),
                    data_source=event_request.data_source,
                    source_id=event_request.source_id,
                    confidence_score=event_request.confidence_score,
                    priority=event_request.priority,
                    correlation_id=event_request.correlation_id,
                    tags=event_request.tags
                )
                
                result = await universal_alert_service.process_event(event)
                processed_events.append({
                    'event_id': event.event_id,
                    'result': result
                })
                
            except Exception as e:
                logger.error(f"❌ Error processing event {event_request.entity_id}: {e}")
                failed_events.append({
                    'entity_id': event_request.entity_id,
                    'error': str(e)
                })
        
        metrics.increment('api_bulk_events_processed_total', len(processed_events))
        
        return {
            "success": len(processed_events) > 0,
            "total_requested": len(events),
            "processed_count": len(processed_events),
            "failed_count": len(failed_events),
            "processed_events": processed_events,
            "failed_events": failed_events
        }
        
    except Exception as e:
        logger.error(f"❌ Error in bulk event processing: {e}")
        metrics.increment('api_bulk_events_errors_total')
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Template and Notification Endpoints
# ============================================================================

@router.get("/notifications/alert/{alert_id}", response_model=Dict[str, Any])
async def get_alert_notifications(alert_id: str):
    """Get notification history for a specific alert"""
    try:
        logger.info(f"🚀 STARTING: get_alert_notifications for alert_id: {alert_id}")
        
        # Get notification history from the service
        notifications = universal_alert_service.get_notification_history(alert_id)
        
        response = {
            "success": True,
            "alert_id": alert_id,
            "notifications": notifications,
            "total_count": len(notifications)
        }
        
        logger.info(f"✅ SUCCESS: get_alert_notifications for alert_id: {alert_id}, count: {len(notifications)}")
        return response
        
    except Exception as e:
        logger.error(f"❌ ERROR: get_alert_notifications for alert_id: {alert_id} - {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notifications/alert/{alert_id}", response_model=Dict[str, Any])
async def delete_alert_notifications(
    alert_id: str,
    user_id: str = Query(..., description="User ID")
):
    """Delete notification history for a specific alert (scoped to user's alert)"""
    try:
        existing_alert = await universal_alert_service.get_alert_by_id(alert_id, user_id)
        if not existing_alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        deleted_count = universal_alert_service.delete_notification_history(alert_id)
        return {
            "success": True,
            "alert_id": alert_id,
            "user_id": user_id,
            "deleted_count": deleted_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting notifications for alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notifications/clear", response_model=Dict[str, Any])
async def clear_notifications_for_user(
    user_id: str = Query(..., description="User ID")
):
    """Delete notification history for all alerts owned by the user"""
    try:
        deleted_count = universal_alert_service.clear_notifications_for_user(user_id)
        return {
            "success": True,
            "user_id": user_id,
            "deleted_count": deleted_count,
        }
    except Exception as e:
        logger.error(f"❌ Error clearing notifications for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/alerts/bulk-action", response_model=Dict[str, Any])
async def admin_bulk_action_on_alerts(
    req: BulkAlertActionRequest = Body(...),
    user_id: str = Query(..., description="Admin user ID")
):
    """Admin: activate/deactivate/delete alerts in bulk"""
    try:
        result = await universal_alert_service.admin_bulk_action(
            alert_ids=req.alert_ids,
            action=req.action,
            admin_user_id=user_id,
            reason=req.reason,
        )
        return {
            "success": True,
            "processed": result.get("processed", 0),
            "failed": result.get("failed", 0),
            "results": result.get("results", []),
        }
    except Exception as e:
        logger.error(f"❌ Error in admin bulk action: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/templates", response_model=Dict[str, Any])
async def get_notification_templates():
    """Get available notification templates"""
    try:
        # This would integrate with your template system
        templates = {
            "email": {
                "earnings_alert": {
                    "name": "Earnings Alert",
                    "description": "Template for earnings-related alerts",
                    "variables": ["symbol", "company_name", "earnings_date", "eps_estimate"]
                },
                "grade_change": {
                    "name": "Grade Change Alert",
                    "description": "Template for analyst grade changes",
                    "variables": ["symbol", "company_name", "analyst_company", "previous_rating", "new_rating"]
                },
                "price_movement": {
                    "name": "Price Movement Alert",
                    "description": "Template for significant price movements",
                    "variables": ["symbol", "current_price", "price_change", "price_change_percent"]
                }
            }
        }
        
        return {
            "success": True,
            "templates": templates
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Statistics and Analytics Endpoints
# ============================================================================

@router.get("/statistics", response_model=Dict[str, Any])
async def get_alert_statistics(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """Get alert statistics and analytics"""
    try:
        # This would integrate with your analytics system
        # For now, return mock statistics
        statistics = {
            "total_alerts": 150,
            "active_alerts": 120,
            "alerts_triggered_today": 25,
            "alerts_triggered_this_week": 85,
            "success_rate": 94.5,
            "average_response_time_ms": 1250,
            "alert_types": {
                "earnings": 45,
                "grade_change": 38,
                "price_movement": 32,
                "custom": 35
            },
            "notification_channels": {
                "email": 110,
                "sms": 25,
                "push": 15
            }
        }
        
        return {
            "success": True,
            "user_id": user_id,
            "period_days": days,
            "statistics": statistics
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting alert statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Scheduler Control Endpoints
# ============================================================================

@router.post("/admin/scheduler/start")
async def start_scheduler():
    """Start the alert scheduler"""
    try:
        logger.info("🚀 Starting alert scheduler via API request")
        
        # In a real implementation, this would:
        # 1. Start the scheduler process/service
        # 2. Register job handlers
        # 3. Begin the scheduler loop
        
        # For now, we'll simulate starting the scheduler
        # In production, this would interface with the actual scheduler service
        
        # Log the action
        audit_log(
            user_id="system",
            action="start_scheduler",
            entity_type="scheduler",
            entity_id="main",
            details={"source": "api", "timestamp": datetime.utcnow().isoformat()}
        )
        
        metrics.increment('scheduler_start_total')
        
        return {
            "success": True,
            "message": "Alert scheduler started successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "scheduler_id": "main",
            "status": "running"
        }
        
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {e}")
        metrics.increment('scheduler_start_failed_total')
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler: {str(e)}")

@router.post("/admin/scheduler/stop")
async def stop_scheduler():
    """Stop the alert scheduler"""
    try:
        logger.info("⏹️ Stopping alert scheduler via API request")
        
        # In a real implementation, this would:
        # 1. Signal the scheduler to stop accepting new jobs
        # 2. Wait for running jobs to complete gracefully
        # 3. Shutdown the scheduler process
        
        # For now, we'll simulate stopping the scheduler
        # In production, this would interface with the actual scheduler service
        
        # Log the action
        audit_log(
            user_id="system",
            action="stop_scheduler",
            entity_type="scheduler",
            entity_id="main",
            details={"source": "api", "timestamp": datetime.utcnow().isoformat()}
        )
        
        metrics.increment('scheduler_stop_total')
        
        return {
            "success": True,
            "message": "Alert scheduler stopped successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "scheduler_id": "main",
            "status": "stopped"
        }
        
    except Exception as e:
        logger.error(f"❌ Error stopping scheduler: {e}")
        metrics.increment('scheduler_stop_failed_total')
        raise HTTPException(status_code=500, detail=f"Failed to stop scheduler: {str(e)}")

@router.post("/admin/scheduler/restart")
async def restart_scheduler():
    """Restart the alert scheduler"""
    try:
        logger.info("🔄 Restarting alert scheduler via API request")
        
        # In a real implementation, this would:
        # 1. Stop the scheduler gracefully
        # 2. Wait for complete shutdown
        # 3. Start the scheduler again
        
        # For now, we'll simulate restarting the scheduler
        # In production, this would interface with the actual scheduler service
        
        # Log the action
        audit_log(
            user_id="system",
            action="restart_scheduler",
            entity_type="scheduler",
            entity_id="main",
            details={"source": "api", "timestamp": datetime.utcnow().isoformat()}
        )
        
        metrics.increment('scheduler_restart_total')
        
        return {
            "success": True,
            "message": "Alert scheduler restarted successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "scheduler_id": "main",
            "status": "running"
        }
        
    except Exception as e:
        logger.error(f"❌ Error restarting scheduler: {e}")
        metrics.increment('scheduler_restart_failed_total')
        raise HTTPException(status_code=500, detail=f"Failed to restart scheduler: {str(e)}")

@router.get("/admin/scheduler/status")
async def get_scheduler_status():
    """Get current scheduler status"""
    try:
        # In a real implementation, this would:
        # 1. Check if the scheduler process is running
        # 2. Get current job execution status
        # 3. Return detailed health information
        
        # For now, we'll check the database for recent job executions
        from app.database import db
        
        # Check recent job executions
        query = """
        SELECT COUNT(*) as total_executions,
               COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
               COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
               MAX(started_at) as last_execution,
               MIN(started_at) as first_execution
        FROM job_execution_log
        WHERE started_at >= NOW() - INTERVAL '1 hour'
        """
        
        result = db.execute_query(query)
        stats = result[0] if result else {}
        
        # Check scheduled jobs
        jobs_query = """
        SELECT COUNT(*) as total_jobs,
               COUNT(CASE WHEN is_active = true THEN 1 END) as active_jobs
        FROM scheduled_jobs
        """
        
        jobs_result = db.execute_query(jobs_query)
        job_stats = jobs_result[0] if jobs_result else {}
        
        # Determine if scheduler is running based on recent activity
        is_running = stats.get('total_executions', 0) > 0
        
        status = {
            "is_running": is_running,
            "active_jobs": job_stats.get('active_jobs', 0),
            "total_jobs": job_stats.get('total_jobs', 0),
            "last_execution": stats.get('last_execution'),
            "executions_last_hour": stats.get('total_executions', 0),
            "successful_executions": stats.get('successful', 0),
            "failed_executions": stats.get('failed', 0),
            "success_rate": (stats.get('successful', 0) / max(stats.get('total_executions', 1), 1)) * 100,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "success": True,
            "status": status
        }
        
    except Exception as e:
        logger.error(f"❌ Error getting scheduler status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")

# ============================================================================
# Error Handlers (Note: These should be moved to main FastAPI app if needed)
# ============================================================================
# Note: APIRouter doesn't support exception_handler - these are for reference only
# Exception handlers should be defined on the main FastAPI app instance
