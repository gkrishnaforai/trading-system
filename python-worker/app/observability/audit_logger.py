"""
Audit logging functionality for Universal Alert System
Provides structured audit trail for all alert operations
"""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from app.observability.logging import get_logger, log_with_context
from app.observability.constants import AUDIT_ACTIONS, generate_tracking_id

logger = get_logger("audit")

def audit_log(
    action: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    details: Optional[Dict[str, Any]] = None,
    timestamp: Optional[datetime] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """
    Log an audit event for compliance and tracking
    
    Args:
        action: The action performed (e.g., 'alert_created', 'alert_updated')
        user_id: ID of the user who performed the action
        resource_type: Type of resource (e.g., 'alert', 'user', 'config')
        resource_id: ID of the resource that was acted upon
        details: Additional details about the action
        timestamp: When the action occurred (defaults to now)
        metadata: Additional metadata for the audit event
    
    Returns:
        The audit tracking ID
    """
    audit_id = generate_tracking_id("audit")
    audit_timestamp = timestamp or datetime.now()
    
    # Validate action
    if action not in AUDIT_ACTIONS:
        logger.warning(f"Unknown audit action: {action}")
    
    # Create audit record
    audit_record = {
        "audit_id": audit_id,
        "timestamp": audit_timestamp.isoformat(),
        "action": action,
        "action_description": AUDIT_ACTIONS.get(action, action),
        "user_id": user_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
        "metadata": metadata or {},
        "ip_address": None,  # Could be extracted from request context
        "user_agent": None,  # Could be extracted from request context
        "session_id": None   # Could be extracted from request context
    }
    
    # Log the audit event
    log_with_context(
        logger,
        20,  # INFO level
        f"🔍 AUDIT: {action}",
        {
            "audit_id": audit_id,
            "action": action,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "timestamp": audit_timestamp.isoformat(),
            "details": details or {}
        },
        correlation_id=audit_id
    )
    
    # In a production environment, you would also:
    # 1. Store in a dedicated audit database table
    # 2. Send to a log aggregation system
    # 3. Create immutable records for compliance
    
    logger.info(f"Audit event logged: {audit_id}")
    
    return audit_id

class AuditLogger:
    """Enhanced audit logger with additional features"""
    
    def __init__(self):
        self.logger = get_logger("audit_enhanced")
    
    def log_alert_creation(self, user_id: str, alert_id: str, alert_details: Dict[str, Any]) -> str:
        """Log alert creation with enhanced details"""
        return audit_log(
            action="alert_created",
            user_id=user_id,
            resource_type="alert",
            resource_id=alert_id,
            details={
                "alert_name": alert_details.get("alert_name"),
                "alert_type": alert_details.get("alert_type"),
                "symbols": alert_details.get("symbols", []),
                "notification_channels": alert_details.get("notification_channels", []),
                "priority_level": alert_details.get("priority_level"),
                "is_test": alert_details.get("is_test", False)
            }
        )
    
    def log_alert_update(self, user_id: str, alert_id: str, old_details: Dict[str, Any], 
                        new_details: Dict[str, Any]) -> str:
        """Log alert update with before/after comparison"""
        changes = self._compare_details(old_details, new_details)
        
        return audit_log(
            action="alert_updated",
            user_id=user_id,
            resource_type="alert",
            resource_id=alert_id,
            details={
                "alert_name": new_details.get("alert_name"),
                "alert_type": new_details.get("alert_type"),
                "changes": changes,
                "previous_name": old_details.get("alert_name"),
                "new_name": new_details.get("alert_name")
            }
        )
    
    def log_alert_deletion(self, user_id: str, alert_id: str, alert_details: Dict[str, Any]) -> str:
        """Log alert deletion with archived details"""
        return audit_log(
            action="alert_deleted",
            user_id=user_id,
            resource_type="alert",
            resource_id=alert_id,
            details={
                "alert_name": alert_details.get("alert_name"),
                "alert_type": alert_details.get("alert_type"),
                "symbols": alert_details.get("symbols", []),
                "notification_channels": alert_details.get("notification_channels", []),
                "was_active": alert_details.get("is_active", False),
                "trigger_count": alert_details.get("trigger_count", 0),
                "created_at": alert_details.get("created_at"),
                "last_triggered_at": alert_details.get("last_triggered_at")
            }
        )
    
    def log_alert_trigger(self, user_id: str, alert_id: str, trigger_details: Dict[str, Any]) -> str:
        """Log alert trigger event"""
        return audit_log(
            action="alert_triggered",
            user_id=user_id,
            resource_type="alert",
            resource_id=alert_id,
            details={
                "trigger_reason": trigger_details.get("reason"),
                "trigger_data": trigger_details.get("data"),
                "notification_sent": trigger_details.get("notification_sent", False),
                "notification_channels": trigger_details.get("notification_channels", [])
            }
        )
    
    def _compare_details(self, old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """Compare old and new details to identify changes"""
        changes = {}
        
        for key in set(old.keys()) | set(new.keys()):
            old_val = old.get(key)
            new_val = new.get(key)
            
            if old_val != new_val:
                changes[key] = {
                    "old": old_val,
                    "new": new_val
                }
        
        return changes

# Global audit logger instance
audit_logger = AuditLogger()
