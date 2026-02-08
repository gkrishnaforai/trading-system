"""
Enhanced Universal Alert Service - Full Implementation
Industry-standard universal alert system with complete plugin integration
Follows SOLID principles, DRY implementation, and full observability
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Protocol
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import json
import asyncio
from contextlib import asynccontextmanager
import re

from app.database import db
from app.observability.logging import get_logger, log_operation_start, log_operation_success, log_operation_failure
from app.observability.metrics import get_metrics
from app.observability.audit import log_event
from app.services.base import BaseService
from app.services.universal_plugins import plugin_registry

logger = get_logger("universal_alert_service_enhanced")
metrics = get_metrics()

class EventStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"

class AlertStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPPRESSED = "suppressed"

class UrgencyLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class EntityType(Enum):
    STOCK = "stock"
    PORTFOLIO = "portfolio"
    MARKET = "market"
    USER = "user"
    SYSTEM = "system"

@dataclass
class UniversalEvent:
    """Universal event structure for ANY event type"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    entity_type: EntityType = EntityType.STOCK
    entity_id: str = ""
    
    event_data: Dict[str, Any] = field(default_factory=dict)
    previous_data: Optional[Dict[str, Any]] = None
    change_metadata: Optional[Dict[str, Any]] = None
    
    event_timestamp: datetime = field(default_factory=datetime.now)
    detected_at: datetime = field(default_factory=datetime.now)
    processed_at: Optional[datetime] = None
    
    data_source: str = ""
    source_id: Optional[str] = None
    confidence_score: float = 1.0
    
    processing_status: EventStatus = EventStatus.PENDING
    error_message: Optional[str] = None
    retry_count: int = 0
    priority: int = 3
    
    correlation_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'entity_type': self.entity_type.value,
            'entity_id': self.entity_id,
            'event_data': self.event_data,
            'previous_data': self.previous_data,
            'change_metadata': self.change_metadata,
            'event_timestamp': self.event_timestamp,
            'detected_at': self.detected_at,
            'processed_at': self.processed_at,
            'data_source': self.data_source,
            'source_id': self.source_id,
            'confidence_score': self.confidence_score,
            'processing_status': self.processing_status.value,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'priority': self.priority,
            'correlation_id': self.correlation_id,
            'parent_event_id': self.parent_event_id,
            'tags': self.tags
        }

@dataclass
class AlertDefinition:
    """Universal alert definition for ANY alert type"""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    alert_name: str = ""
    alert_type: str = ""
    alert_category: str = "custom"
    
    entity_filters: Dict[str, Any] = field(default_factory=dict)
    event_filters: Dict[str, Any] = field(default_factory=dict)
    trigger_conditions: Dict[str, Any] = field(default_factory=dict)
    suppression_rules: Dict[str, Any] = field(default_factory=dict)
    
    notification_config: Dict[str, Any] = field(default_factory=dict)
    template_config: Dict[str, Any] = field(default_factory=dict)
    priority_level: int = 3
    is_active: bool = True
    is_test: bool = False
    
    trigger_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_triggered_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'alert_id': self.alert_id,
            'user_id': self.user_id,
            'alert_name': self.alert_name,
            'alert_type': self.alert_type,
            'alert_category': self.alert_category,
            'entity_filters': self.entity_filters,
            'event_filters': self.event_filters,
            'trigger_conditions': self.trigger_conditions,
            'suppression_rules': self.suppression_rules,
            'notification_config': self.notification_config,
            'template_config': self.template_config,
            'priority_level': self.priority_level,
            'is_active': self.is_active,
            'is_test': self.is_test,
            'trigger_count': self.trigger_count,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'last_triggered_at': self.last_triggered_at
        }

class UniversalEventRepository(BaseService):
    """Repository for universal events - Single Responsibility Principle"""
    
    async def save_event(self, event: UniversalEvent) -> bool:
        """Save universal event to database"""
        try:
            query = """
                INSERT INTO universal_events (
                    event_id, event_type, entity_type, entity_id, event_data,
                    previous_data, change_metadata, event_timestamp, detected_at,
                    data_source, source_id, confidence_score, processing_status,
                    retry_count, priority, correlation_id, parent_event_id, tags
                ) VALUES (
                    :event_id, :event_type, :entity_type, :entity_id, :event_data,
                    :previous_data, :change_metadata, :event_timestamp, :detected_at,
                    :data_source, :source_id, :confidence_score, :processing_status,
                    :retry_count, :priority, :correlation_id, :parent_event_id, :tags
                )
                ON CONFLICT (event_id) DO UPDATE SET
                    event_timestamp = COALESCE(EXCLUDED.event_timestamp, universal_events.event_timestamp),
                    detected_at = COALESCE(EXCLUDED.detected_at, universal_events.detected_at),
                    event_data = COALESCE(EXCLUDED.event_data, universal_events.event_data),
                    previous_data = COALESCE(EXCLUDED.previous_data, universal_events.previous_data),
                    change_metadata = COALESCE(EXCLUDED.change_metadata, universal_events.change_metadata),
                    data_source = COALESCE(EXCLUDED.data_source, universal_events.data_source),
                    source_id = COALESCE(EXCLUDED.source_id, universal_events.source_id),
                    confidence_score = COALESCE(EXCLUDED.confidence_score, universal_events.confidence_score),
                    priority = COALESCE(EXCLUDED.priority, universal_events.priority),
                    tags = COALESCE(EXCLUDED.tags, universal_events.tags),
                    retry_count = COALESCE(EXCLUDED.retry_count, universal_events.retry_count),
                    error_message = EXCLUDED.error_message,
                    processing_status = CASE
                        WHEN universal_events.processing_status IN ('completed', 'processing')
                            THEN universal_events.processing_status
                        ELSE EXCLUDED.processing_status
                    END,
                    processed_at = CASE
                        WHEN universal_events.processing_status = 'completed'
                            THEN universal_events.processed_at
                        ELSE EXCLUDED.processed_at
                    END,
                    updated_at = NOW()
            """
            
            params = event.to_dict()
            for field in ['event_data', 'previous_data', 'change_metadata']:
                if field in params and params[field] is not None:
                    params[field] = json.dumps(params[field])
            result = db.execute_update(query, params)
            
            if result > 0:
                metrics.increment('universal_events_saved_total')
                self.log_debug(f"✅ Saved universal event {event.event_id}")
                return True
            
            return False
            
        except Exception as e:
            self.log_error("Error saving universal event", e, {'event_id': event.event_id})
            metrics.increment('universal_events_save_errors_total')
            return False
    
    async def get_pending_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get pending events for processing"""
        try:
            query = """
                SELECT * FROM universal_events
                WHERE processing_status = 'pending'
            """
            params = {}
            
            if event_type:
                query += " AND event_type = :event_type"
                params["event_type"] = event_type
            
            query += " ORDER BY priority DESC, detected_at ASC LIMIT :limit"
            params["limit"] = limit
            
            rows = db.execute_query(query, params)
            events = [dict(row) for row in rows]
            
            metrics.set_gauge('universal_events_pending_count', len(events))
            return events
            
        except Exception as e:
            self.log_error("Error getting pending events", e)
            return []
    
    async def update_event_status(self, event_id: str, status: EventStatus, error_message: Optional[str] = None) -> bool:
        """Update event processing status"""
        try:
            query = """
                UPDATE universal_events
                SET processing_status = :status,
                    processed_at = CASE WHEN :status = 'completed' THEN NOW() ELSE processed_at END,
                    error_message = :error_message,
                    updated_at = NOW()
                WHERE event_id = :event_id
            """
            
            params = {
                "event_id": event_id,
                "status": status.value,
                "error_message": error_message
            }
            
            result = db.execute_update(query, params)
            
            if result > 0:
                metrics.increment('universal_events_updated_total')
                self.log_debug(f"✅ Updated event {event_id} status to {status.value}")
                return True
            
            return False
            
        except Exception as e:
            self.log_error("Error updating event status", e, {'event_id': event_id})
            return False

class AlertDefinitionRepository(BaseService):
    """Repository for alert definitions - Single Responsibility Principle"""
    
    async def save_alert(self, alert: AlertDefinition) -> bool:
        """Save alert definition to database"""
        try:
            query = """
                INSERT INTO universal_alerts (
                    alert_id, user_id, alert_name, alert_type, alert_category,
                    entity_filters, event_filters, trigger_conditions, suppression_rules,
                    notification_config, template_config, priority_level, is_active, is_test
                ) VALUES (
                    :alert_id, :user_id, :alert_name, :alert_type, :alert_category,
                    :entity_filters, :event_filters, :trigger_conditions, :suppression_rules,
                    :notification_config, :template_config, :priority_level, :is_active, :is_test
                )
                ON CONFLICT (alert_id) DO UPDATE SET
                    alert_name = EXCLUDED.alert_name,
                    entity_filters = EXCLUDED.entity_filters,
                    event_filters = EXCLUDED.event_filters,
                    trigger_conditions = EXCLUDED.trigger_conditions,
                    suppression_rules = EXCLUDED.suppression_rules,
                    notification_config = EXCLUDED.notification_config,
                    template_config = EXCLUDED.template_config,
                    priority_level = EXCLUDED.priority_level,
                    is_active = EXCLUDED.is_active,
                    updated_at = NOW()
            """
            
            params = alert.to_dict()
            # Convert dict fields to JSON for PostgreSQL
            import json
            for field in ['entity_filters', 'event_filters', 'trigger_conditions', 'suppression_rules', 'notification_config', 'template_config']:
                if field in params and params[field] is not None:
                    params[field] = json.dumps(params[field])
            
            result = db.execute_update(query, params)
            
            if result > 0:
                metrics.increment('universal_alerts_saved_total')
                self.log_debug(f"✅ Saved alert definition {alert.alert_id}")
                return True
            
            return False
            
        except Exception as e:
            self.log_error("Error saving alert definition", e, {'alert_id': alert.alert_id})
            return False
    
    async def get_alert_by_id(self, alert_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get alert by ID and user ID"""
        try:
            query = """
                SELECT * FROM universal_alerts
                WHERE alert_id = :alert_id
                  AND user_id = :user_id
            """
            
            params = {"alert_id": alert_id, "user_id": user_id}
            rows = db.execute_query(query, params)
            
            if rows:
                return dict(rows[0])
            return None
            
        except Exception as e:
            self.log_error("Error getting alert by ID", e, {'alert_id': alert_id, 'user_id': user_id})
            return None
    
    async def update_alert(self, alert_def: AlertDefinition) -> bool:
        """Update an existing alert definition"""
        try:
            query = """
                UPDATE universal_alerts
                SET alert_name = :alert_name,
                    alert_type = :alert_type,
                    alert_category = :alert_category,
                    entity_filters = :entity_filters,
                    event_filters = :event_filters,
                    trigger_conditions = :trigger_conditions,
                    suppression_rules = :suppression_rules,
                    notification_config = :notification_config,
                    template_config = :template_config,
                    priority_level = :priority_level,
                    is_active = :is_active,
                    is_test = :is_test,
                    updated_at = NOW()
                WHERE alert_id = :alert_id
                  AND user_id = :user_id
            """
            
            params = alert_def.to_dict()
            # Convert dict fields to JSON for PostgreSQL
            import json
            for field in ['entity_filters', 'event_filters', 'trigger_conditions', 'suppression_rules', 'notification_config', 'template_config']:
                if field in params and params[field] is not None:
                    params[field] = json.dumps(params[field])
            
            result = db.execute_update(query, params)
            
            if result > 0:
                metrics.increment('universal_alerts_updated_total')
                self.log_debug(f"✅ Updated alert definition {alert_def.alert_id}")
                return True
            
            return False
            
        except Exception as e:
            self.log_error("Error updating alert definition", e, {'alert_id': alert_def.alert_id})
            return False
    
    async def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """Delete an alert definition"""
        try:
            query = """
                DELETE FROM universal_alerts
                WHERE alert_id = :alert_id
                  AND user_id = :user_id
            """
            
            params = {"alert_id": alert_id, "user_id": user_id}
            result = db.execute_update(query, params)
            
            if result > 0:
                metrics.increment('universal_alerts_deleted_total')
                self.log_debug(f"✅ Deleted alert definition {alert_id}")
                return True
            
            return False
            
        except Exception as e:
            self.log_error("Error deleting alert definition", e, {'alert_id': alert_id})
            return False
    
    async def get_active_alerts_for_event(self, event: UniversalEvent) -> List[Dict[str, Any]]:
        """Get active alerts that might be triggered by this event"""
        try:
            query = """
                SELECT * FROM universal_alerts
                WHERE is_active = true
                  AND alert_type = :event_type
                  AND user_id IS NOT NULL
            """
            
            params = {"event_type": event.event_type}
            rows = db.execute_query(query, params)
            
            # Filter alerts based on entity and event filters
            matching_alerts = []
            for row in rows:
                alert = dict(row)
                
                # Check entity filters
                if self._matches_entity_filters(alert, event):
                    # Check event filters
                    if self._matches_event_filters(alert, event):
                        matching_alerts.append(alert)
            
            metrics.set_gauge('universal_alerts_matching_count', len(matching_alerts))
            return matching_alerts
            
        except Exception as e:
            self.log_error("Error getting active alerts", e)
            return []
    
    def _matches_entity_filters(self, alert: Dict[str, Any], event: UniversalEvent) -> bool:
        """Check if event matches alert's entity filters"""
        entity_filters = alert.get('entity_filters', {})
        
        # Check entity type
        if 'entity_types' in entity_filters:
            if event.entity_type.value not in entity_filters['entity_types']:
                return False
        
        # Check specific entities
        if 'entities' in entity_filters:
            if event.entity_id not in entity_filters['entities']:
                return False
        
        # Check symbols (for stock entities)
        if 'symbols' in entity_filters and event.entity_type == EntityType.STOCK:
            if event.entity_id not in entity_filters['symbols']:
                return False
        
        return True
    
    def _matches_event_filters(self, alert: Dict[str, Any], event: UniversalEvent) -> bool:
        """Check if event matches alert's event filters"""
        event_filters = alert.get('event_filters', {})
        
        # Check priority
        if 'min_priority' in event_filters:
            if event.priority < event_filters['min_priority']:
                return False
        
        # Check confidence
        if 'min_confidence' in event_filters:
            if event.confidence_score < event_filters['min_confidence']:
                return False
        
        # Check data source
        if 'data_sources' in event_filters:
            if event.data_source not in event_filters['data_sources']:
                return False
        
        return True

class UniversalAlertServiceEnhanced(BaseService):
    """Main universal alert service - Orchestrates all components"""
    
    def __init__(self):
        super().__init__()
        self.event_repo = UniversalEventRepository()
        self.alert_repo = AlertDefinitionRepository()
        self.plugin_registry = plugin_registry
    
    async def get_alert_by_id(self, alert_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get alert by ID and user ID"""
        return await self.alert_repo.get_alert_by_id(alert_id, user_id)
    
    async def create_alert(self, user_id: str, alert_def: AlertDefinition) -> str:
        """Create a new universal alert with full audit trail"""
        tracking_id = log_operation_start(
            logger, "create_alert",
            {'user_id': user_id, 'alert_type': alert_def.alert_type, 'alert_name': alert_def.alert_name}
        )
        
        try:
            # Log operation start to audit trail
            log_event(
                level='info',
                operation='create_alert',
                message=f"Creating alert: {alert_def.alert_name}",
                context={
                    'alert_id': alert_def.alert_id,
                    'user_id': user_id,
                    'alert_type': alert_def.alert_type
                }
            )
            alert_def.user_id = user_id
            success = await self.alert_repo.save_alert(alert_def)
            
            if success:
                log_operation_success(
                    logger, "create_alert", tracking_id,
                    {'alert_id': alert_def.alert_id, 'user_id': user_id}
                )
                
                log_event(
                    level='info',
                    operation='create_alert',
                    message=f"Successfully created alert: {alert_def.alert_name}",
                    context={
                        'alert_id': alert_def.alert_id,
                        'user_id': user_id,
                        'alert_type': alert_def.alert_type,
                        'success': True
                    }
                )
                
                metrics.increment('universal_alerts_created_total', labels={'alert_type': alert_def.alert_type})
                self.log_info(f"✅ Created alert {alert_def.alert_id} for user {user_id}")
                return alert_def.alert_id
            else:
                raise Exception("Failed to save alert to database")
                
        except Exception as e:
            log_operation_failure(logger, "create_alert", tracking_id, e)
            
            log_event(
                level='error',
                operation='create_alert',
                message=f"Failed to create alert: {alert_def.alert_name}",
                exception=e,
                context={
                    'alert_id': alert_def.alert_id,
                    'user_id': user_id,
                    'error': str(e)
                }
            )
            
            metrics.increment('universal_alerts_create_errors_total')
            self.log_error("Error creating alert", e, {'user_id': user_id})
            return ""
    
    async def update_alert(self, user_id: str, alert_id: str, alert_def: AlertDefinition) -> bool:
        """Update an existing alert with full audit trail"""
        tracking_id = log_operation_start(
            logger, "update_alert",
            {'user_id': user_id, 'alert_id': alert_id, 'alert_name': alert_def.alert_name}
        )
        
        try:
            # Log update start
            log_event(
                level='info',
                operation='update_alert',
                message=f"Updating alert: {alert_def.alert_name}",
                context={
                    'alert_id': alert_id,
                    'user_id': user_id,
                    'alert_type': alert_def.alert_type
                }
            )
            
            # Verify alert exists and belongs to user
            existing_alert = await self.alert_repo.get_alert_by_id(alert_id, user_id)
            if not existing_alert:
                log_operation_failure(
                    logger, "update_alert", tracking_id,
                    ValueError(f"Alert {alert_id} not found or access denied for user {user_id}")
                )
                return False
            
            # Update alert definition
            alert_def.user_id = user_id
            alert_def.alert_id = alert_id  # Ensure ID is preserved
            
            success = await self.alert_repo.update_alert(alert_def)
            
            if success:
                log_operation_success(
                    logger, "update_alert", tracking_id,
                    {
                        'alert_id': alert_id,
                        'user_id': user_id,
                        'alert_name': alert_def.alert_name,
                        'previous_name': existing_alert.get('alert_name', 'Unknown'),
                        'new_name': alert_def.alert_name
                    }
                )
                
                # Log update event
                log_event(
                    level='info',
                    operation='update_alert',
                    message=f"Successfully updated alert: {alert_def.alert_name}",
                    context={
                        'alert_id': alert_id,
                        'user_id': user_id,
                        'alert_type': alert_def.alert_type,
                        'success': True
                    }
                )
                
                metrics.increment('universal_alerts_updated_total')
                self.log_info(f"✅ Updated alert {alert_id} for user {user_id}")
                return True
            else:
                raise Exception("Failed to update alert in database")
                
        except Exception as e:
            log_operation_failure(logger, "update_alert", tracking_id, e)
            return False
    
    async def delete_alert(self, user_id: str, alert_id: str) -> bool:
        """Delete an existing alert with full audit trail"""
        tracking_id = log_operation_start(
            logger, "delete_alert",
            {'user_id': user_id, 'alert_id': alert_id}
        )
        
        try:
            # Log delete start
            log_event(
                level='info',
                operation='delete_alert',
                message=f"Deleting alert: {alert_id}",
                context={
                    'alert_id': alert_id,
                    'user_id': user_id
                }
            )
            
            # Verify alert exists and belongs to user
            existing_alert = await self.alert_repo.get_alert_by_id(alert_id, user_id)
            if not existing_alert:
                log_operation_failure(
                    logger, "delete_alert", tracking_id,
                    ValueError(f"Alert {alert_id} not found or access denied for user {user_id}")
                )
                return False
            
            # Delete alert
            success = await self.alert_repo.delete_alert(alert_id, user_id)
            
            if success:
                log_operation_success(
                    logger, "delete_alert", tracking_id,
                    {
                        'alert_id': alert_id,
                        'user_id': user_id,
                        'deleted_alert_name': existing_alert.get('alert_name', 'Unknown'),
                        'deleted_alert_type': existing_alert.get('alert_type', 'Unknown')
                    }
                )
                
                # Log delete event
                log_event(
                    level='info',
                    operation='delete_alert',
                    message=f"Successfully deleted alert: {existing_alert.get('alert_name', 'Unknown')}",
                    context={
                        'alert_id': alert_id,
                        'user_id': user_id,
                        'alert_name': existing_alert.get('alert_name', 'Unknown'),
                        'success': True
                    }
                )
                
                metrics.increment('universal_alerts_deleted_total')
                self.log_info(f"✅ Deleted alert {alert_id} for user {user_id}")
                return True
            else:
                raise Exception("Failed to delete alert in database")
                
        except Exception as e:
            log_operation_failure(logger, "delete_alert", tracking_id, e)
            return False
    
    async def get_user_alerts(self, user_id: str, page: int = 1, limit: int = 50, alert_type: str = None) -> List[Dict[str, Any]]:
        """Get alerts for a specific user"""
        try:
            query = """
                SELECT * FROM universal_alerts
                WHERE user_id = :user_id AND is_active = true
            """
            
            params = {"user_id": user_id, "limit": limit, "offset": (page - 1) * limit}
            
            if alert_type:
                query += " AND alert_type = :alert_type"
                params["alert_type"] = alert_type
            
            query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            
            rows = db.execute_query(query, params)
            return [dict(row) for row in rows]
            
        except Exception as e:
            self.log_error("Error getting user alerts", e, {'user_id': user_id})
            return []
    
    async def get_user_alerts_count(self, user_id: str, alert_type: str = None) -> int:
        """Get total count of alerts for a user"""
        try:
            query = """
                SELECT COUNT(*) as total FROM universal_alerts
                WHERE user_id = :user_id
            """
            
            params = {"user_id": user_id}
            
            if alert_type:
                query += " AND alert_type = :alert_type"
                params["alert_type"] = alert_type
            
            rows = db.execute_query(query, params)
            return rows[0]['total'] if rows else 0
            
        except Exception as e:
            self.log_error("Error getting user alerts count", e, {'user_id': user_id})
            return 0
    
    async def get_all_alerts(self, page: int = 1, limit: int = 50, alert_type: str = None) -> List[Dict[str, Any]]:
        """Get all alerts (admin function)"""
        try:
            query = """
                SELECT * FROM universal_alerts
            """
            
            params = {"limit": limit, "offset": (page - 1) * limit}
            
            if alert_type:
                query += " WHERE alert_type = :alert_type"
                params["alert_type"] = alert_type
            
            query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            
            rows = db.execute_query(query, params)
            return [dict(row) for row in rows]
            
        except Exception as e:
            self.log_error("Error getting all alerts", e)
            return []
    
    async def get_all_alerts_count(self, alert_type: str = None) -> int:
        """Get total count of all alerts"""
        try:
            query = """
                SELECT COUNT(*) as total FROM universal_alerts
            """
            
            params = {}
            
            if alert_type:
                query += " WHERE alert_type = :alert_type"
                params["alert_type"] = alert_type
            
            rows = db.execute_query(query, params)
            return rows[0]['total'] if rows else 0
            
        except Exception as e:
            self.log_error("Error getting all alerts count", e)
            return 0
    
    async def process_event(self, event: UniversalEvent) -> Dict[str, Any]:
        """Process a universal event and trigger matching alerts"""
        tracking_id = log_operation_start(
            logger, "process_event",
            {'event_id': event.event_id, 'event_type': event.event_type, 'entity_id': event.entity_id}
        )
        
        start_time = datetime.now()
        
        try:
            # Log event processing start
            log_event(
                level='info',
                operation='process_event',
                message=f"Processing event: {event.event_id}",
                context={'event_data': event.to_dict()}
            )
            
            # Update event status to processing
            await self.event_repo.update_event_status(event.event_id, EventStatus.PROCESSING)
            
            # Get matching alerts
            matching_alerts = await self.alert_repo.get_active_alerts_for_event(event)
            
            triggered_alerts = []
            failed_alerts = []
            
            for alert_data in matching_alerts:
                try:
                    # Get appropriate evaluator plugin
                    evaluator = self.plugin_registry.get_evaluator_plugin(event.event_type)
                    if evaluator:
                        result = await evaluator.evaluate(event.to_dict(), alert_data)
                        if result.get('should_trigger', False):
                            # Create alert event
                            await self._create_alert_event(event, alert_data, result)
                            triggered_alerts.append(alert_data['alert_id'])
                    
                except Exception as e:
                    self.log_error("Error evaluating alert", e, {'alert_id': alert_data.get('alert_id')})
                    failed_alerts.append(alert_data.get('alert_id'))
            
            # Update event status to completed
            await self.event_repo.update_event_status(event.event_id, EventStatus.COMPLETED)
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            log_operation_success(
                logger, "process_event", tracking_id,
                {
                    'event_id': event.event_id,
                    'alerts_evaluated': len(matching_alerts),
                    'alerts_triggered': len(triggered_alerts),
                    'alerts_failed': len(failed_alerts),
                    'duration_ms': duration_ms
                }
            )
            
            log_event(
                level='info',
                operation='process_event',
                message=f"Successfully processed event: {event.event_id}",
                duration_ms=duration_ms,
                context={
                    'alerts_evaluated': len(matching_alerts),
                    'alerts_triggered': len(triggered_alerts),
                    'failed_alerts': len(failed_alerts)
                }
            )
            
            metrics.record_duration('event_processing_duration_ms', duration_ms / 1000)
            metrics.increment('universal_events_processed_total')
            metrics.increment('universal_alerts_triggered_total')
            
            self.log_info(f"✅ Processed event {event.event_id}, triggered {len(triggered_alerts)} alerts")
            
            return {
                'success': True,
                'event_id': event.event_id,
                'alerts_evaluated': len(matching_alerts),
                'alerts_triggered': len(triggered_alerts),
                'alerts_failed': len(failed_alerts),
                'triggered_alert_ids': triggered_alerts,
                'duration_ms': duration_ms
            }
            
        except Exception as e:
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            await self.event_repo.update_event_status(event.event_id, EventStatus.FAILED, str(e))
            
            log_operation_failure(logger, "process_event", tracking_id, e)
            
            log_event(
                level='error',
                operation='process_event',
                message=f"Failed to process event: {event.event_id}",
                duration_ms=duration_ms,
                exception=e,
                context={'error': str(e)}
            )
            
            metrics.increment('universal_events_process_errors_total')
            self.log_error("Error processing event", e, {'event_id': event.event_id})
            
            return {
                'success': False,
                'error': str(e),
                'event_id': event.event_id,
                'duration_ms': duration_ms
            }
    
    async def _create_alert_event(self, event: UniversalEvent, alert_data: Dict[str, Any], evaluation_result: Dict[str, Any]):
        """Create an alert event when an alert is triggered"""
        try:
            alert_event_id = str(uuid.uuid4())
            
            query = """
                INSERT INTO universal_alert_events (
                    event_id, alert_id, universal_event_id, user_id,
                    match_score, trigger_reason, trigger_details, urgency_level,
                    status, correlation_id
                ) VALUES (
                    :event_id, :alert_id, :universal_event_id, :user_id,
                    :match_score, :trigger_reason, CAST(:trigger_details AS jsonb), :urgency_level,
                    'pending', :correlation_id
                )
            """
            
            params = {
                'event_id': alert_event_id,
                'alert_id': alert_data['alert_id'],
                'universal_event_id': event.event_id,
                'user_id': alert_data['user_id'],
                'match_score': evaluation_result.get('match_score', 0.0),
                'trigger_reason': evaluation_result.get('trigger_reason', ''),
                'trigger_details': json.dumps(evaluation_result.get('trigger_details', {}) or {}),
                'urgency_level': evaluation_result.get('urgency_level', 'medium'),
                'correlation_id': event.correlation_id
            }
            
            db.execute_update(query, params)
            
            # Update alert statistics
            await self._update_alert_statistics(alert_data['alert_id'])
            
            # Queue notifications
            await self._queue_notifications(alert_event_id, alert_data, evaluation_result)
            
            metrics.increment('universal_alert_events_created_total')
            self.log_debug(f"✅ Created alert event {alert_event_id}")
            
        except Exception as e:
            self.log_error("Error creating alert event", e)
    
    async def _update_alert_statistics(self, alert_id: str):
        """Update alert trigger statistics"""
        try:
            query = """
                UPDATE universal_alerts
                SET trigger_count = trigger_count + 1,
                    last_triggered_at = NOW(),
                    success_count = success_count + 1
                WHERE alert_id = :alert_id
            """
            
            db.execute_update(query, {"alert_id": alert_id})
            
        except Exception as e:
            self.log_error("Error updating alert statistics", e, {'alert_id': alert_id})
    
    async def _queue_notifications(self, alert_event_id: str, alert_data: Dict[str, Any], evaluation_result: Dict[str, Any]):
        """Queue notifications for triggered alert"""
        try:
            notification_config = alert_data.get('notification_config', {})
            channels = notification_config.get('channels', ['email'])
            
            for channel in channels:
                # Get notification plugin
                plugin = self.plugin_registry.get_notification_plugin(channel)
                if plugin:
                    await self._create_notification_queue_item(alert_event_id, channel, alert_data, evaluation_result)
            
        except Exception as e:
            self.log_error("Error queuing notifications", e, {'alert_event_id': alert_event_id})
    
    async def _create_notification_queue_item(self, alert_event_id: str, channel: str, alert_data: Dict[str, Any], evaluation_result: Dict[str, Any]):
        """Create notification queue item"""
        try:
            queue_id = str(uuid.uuid4())
            
            query = """
                INSERT INTO universal_notification_queue (
                    queue_id, alert_event_id, channel_type, recipient, user_email,
                    subject, message_body, html_body, template_data,
                    status, created_at
                ) VALUES (
                    :queue_id, :alert_event_id, :channel_type, :recipient, :user_email,
                    :subject, :message_body, :html_body, CAST(:template_data AS jsonb),
                    'pending', NOW()
                )
            """
            
            user_id = alert_data.get('user_id')
            user_email = await self._resolve_user_email(user_id) if user_id else None

            # Backward-compat: keep recipient populated, but for email channel prefer actual email
            recipient = user_email if (channel == 'email' and user_email) else (str(user_id) if user_id else '')

            # Idempotency: do not re-queue the same alert_event/channel/recipient on restarts
            # This prevents duplicate emails when historical events are reprocessed.
            try:
                dedupe_query = """
                    SELECT 1
                    FROM universal_notification_queue
                    WHERE alert_event_id = :alert_event_id
                      AND channel_type = :channel_type
                      AND (
                        recipient = :recipient
                        OR (user_email IS NOT NULL AND user_email = :user_email)
                      )
                    LIMIT 1
                """
                existing = db.execute_query(
                    dedupe_query,
                    {
                        "alert_event_id": alert_event_id,
                        "channel_type": channel,
                        "recipient": recipient,
                        "user_email": user_email,
                    },
                )
                if existing:
                    metrics.increment('universal_notifications_deduped_total')
                    return
            except Exception:
                # If dedupe check fails, proceed with insert to avoid dropping notifications.
                pass
            
            # Generate message content
            subject = f"Alert: {evaluation_result.get('trigger_reason', 'Alert Triggered')}"
            message_body = self._generate_text_message(evaluation_result)
            html_body = self._generate_html_message(evaluation_result)
            
            params = {
                'queue_id': queue_id,
                'alert_event_id': alert_event_id,
                'channel_type': channel,
                'recipient': recipient,
                'user_email': user_email,
                'subject': subject,
                'message_body': message_body,
                'html_body': html_body,
                'template_data': json.dumps(evaluation_result.get('trigger_details', {}) or {})
            }
            
            db.execute_update(query, params)
            metrics.increment('universal_notifications_queued_total')
            
        except Exception as e:
            self.log_error("Error creating notification queue item", e)

    async def _resolve_user_email(self, user_id: str) -> Optional[str]:
        """Resolve user's email from DB.

        Returns None if not found/invalid.
        """
        try:
            query = """
                SELECT email
                FROM users
                WHERE id = :user_id
                LIMIT 1
            """
            rows = db.execute_query(query, {"user_id": user_id})
            email = rows[0].get('email') if rows else None
            if not email:
                return None
            email = str(email).strip()
            # Lightweight validation (avoid queuing clearly invalid emails)
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                return None
            return email
        except Exception as e:
            self.log_error("Error resolving user email", e, {'user_id': user_id})
            return None
    
    def _generate_text_message(self, evaluation_result: Dict[str, Any]) -> str:
        """Generate text message for notification"""
        trigger_reason = evaluation_result.get('trigger_reason', 'Alert triggered')
        details = evaluation_result.get('trigger_details', {})
        
        message = f"""
ALERT: {trigger_reason}

Details:
"""
        
        for key, value in details.items():
            message += f"- {key.replace('_', ' ').title()}: {value}\n"
        
        message += f"\nTriggered at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return message.strip()
    
    def _generate_html_message(self, evaluation_result: Dict[str, Any]) -> str:
        """Generate HTML message for notification"""
        trigger_reason = evaluation_result.get('trigger_reason', 'Alert triggered')
        details = evaluation_result.get('trigger_details', {})
        urgency = evaluation_result.get('urgency_level', 'medium')
        
        # Color based on urgency
        colors = {
            'low': '#28a745',
            'medium': '#ffc107',
            'high': '#fd7e14',
            'critical': '#dc3545'
        }
        color = colors.get(urgency, '#ffc107')
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Alert Notification</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .alert-header {{ background: {color}; color: white; padding: 15px; border-radius: 5px; }}
        .alert-content {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .detail-item {{ margin: 8px 0; }}
        .detail-label {{ font-weight: bold; }}
    </style>
</head>
<body>
    <div class="alert-header">
        <h2>🔔 Alert Notification</h2>
        <p>{trigger_reason}</p>
    </div>
    
    <div class="alert-content">
        <h3>Details:</h3>
"""
        
        for key, value in details.items():
            html += f"""
        <div class="detail-item">
            <span class="detail-label">{key.replace('_', ' ').title()}:</span> {value}
        </div>
"""
        
        html += f"""
        <div class="detail-item">
            <span class="detail-label">Triggered at:</span> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    async def collect_data_from_plugins(self, plugin_configs: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Collect data from multiple data source plugins"""
        results = {}
        
        for plugin_name, config in plugin_configs.items():
            try:
                plugin = self.plugin_registry.get_data_source_plugin(plugin_name)
                if plugin:
                    events = await plugin.collect_data(config)
                    results[plugin_name] = events
                    
                    # Save events to database
                    for event_data in events:
                        event_source_id = event_data.get('source_id')
                        event_data_source = event_data.get('data_source', plugin_name)
                        derived_event_id: Optional[str] = None
                        if not event_data.get('event_id') and event_source_id:
                            derived_event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{event_data_source}:{event_source_id}"))

                        event = UniversalEvent(
                            event_id=event_data.get('event_id') or derived_event_id or str(uuid.uuid4()),
                            event_type=event_data.get('event_type'),
                            entity_type=EntityType(event_data.get('entity_type', 'stock')),
                            entity_id=event_data.get('entity_id'),
                            event_data=event_data.get('event_data'),
                            event_timestamp=event_data.get('event_timestamp', datetime.now()),
                            data_source=event_data_source,
                            source_id=event_source_id,
                            confidence_score=event_data.get('confidence_score', 1.0)
                        )
                        await self.event_repo.save_event(event)
                
            except Exception as e:
                self.log_error(f"Error collecting data from plugin {plugin_name}", e)
                results[plugin_name] = []
        
        return results
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get system health status"""
        try:
            # Get pending events count
            pending_events = await self.event_repo.get_pending_events(limit=1000)
            
            # Get plugin status
            plugins = self.plugin_registry.list_plugins()
            
            # Get metrics
            current_metrics = metrics.get_metrics()
            
            health_status = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'pending_events': len(pending_events),
                'plugins': plugins,
                'metrics': current_metrics,
                'checks': {
                    'database': 'healthy',  # Would implement actual DB health check
                    'plugins': 'healthy',
                    'queues': 'healthy'
                }
            }
            
            # Determine overall health
            if len(pending_events) > 1000:
                health_status['status'] = 'degraded'
                health_status['checks']['queues'] = 'overloaded'
            
            return health_status
            
        except Exception as e:
            self.log_error("Error getting system health", e)
            return {
                'status': 'unhealthy',
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    # ============================================================================
    # ADMIN MANAGEMENT METHODS
    # ============================================================================
    
    async def admin_get_all_alerts(
        self, 
        page: int = 1, 
        limit: int = 50, 
        status: Optional[str] = None, 
        alert_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Admin: Get all alerts across all users with pagination"""
        print(f"ADMIN GET ALL ALERTS CALLED: page={page}, limit={limit}, status={status}, alert_type={alert_type}")
        try:
            offset = (page - 1) * limit
            
            query = """
                SELECT alert_id, user_id, alert_name, alert_type, alert_category,
                       is_active, is_test, trigger_count, success_count, failure_count,
                       last_triggered_at, created_at, updated_at
                FROM universal_alerts
                WHERE 1=1
            """
            params = {}
            
            if status:
                if status == 'active':
                    query += " AND is_active = true"
                elif status == 'inactive':
                    query += " AND is_active = false"
                elif status == 'test':
                    query += " AND is_test = true"
                elif status == 'production':
                    query += " AND is_test = false"
                params['status'] = status
            
            if alert_type:
                query += " AND alert_type = :alert_type"
                params['alert_type'] = alert_type
            
            # Get total count (before adding ORDER BY)
            count_query = query.replace(
                "SELECT alert_id, user_id, alert_name, alert_type, alert_category, is_active, is_test, trigger_count, success_count, failure_count, last_triggered_at, created_at, updated_at",
                "SELECT COUNT(*) as total"
            )
            total_result = db.execute_query(count_query, params)
            self.log_info(f"COUNT query result: {total_result}")
            total = total_result[0]['total'] if total_result and len(total_result) > 0 and 'total' in total_result[0] else 0
            
            # Get paginated results
            query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            params['limit'] = limit
            params['offset'] = offset
            
            rows = db.execute_query(query, params)
            alerts = [dict(row) for row in rows]
            
            return {
                'alerts': alerts,
                'total': total,
                'page': page,
                'limit': limit,
                'total_pages': (total + limit - 1) // limit
            }
            
        except Exception as e:
            self.log_error("Error getting admin alerts", e)
            return {'alerts': [], 'total': 0}
    
    async def admin_get_audit_trail(
            self,
            entity_type: Optional[str] = None,
            operation_type: Optional[str] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
            page: int = 1,
            limit: int = 100
        ) -> Dict[str, Any]:
        """Admin: Get comprehensive audit trail"""
        try:
            offset = (page - 1) * limit
            
            query = """
                SELECT audit_id, entity_type, entity_id, entity_name, operation_type,
                       status, started_at, completed_at, duration_ms, user_id,
                       operation_data, error_message, impact_level
                FROM alert_audit_trail
                WHERE 1=1
            """
            params = {}
            
            if entity_type:
                query += " AND entity_type = :entity_type"
                params['entity_type'] = entity_type
            
            if operation_type:
                query += " AND operation_type = :operation_type"
                params['operation_type'] = operation_type
            
            if start_date:
                query += " AND started_at >= :start_date"
                params['start_date'] = start_date
            
            if end_date:
                query += " AND started_at <= :end_date"
                params['end_date'] = end_date + ' 23:59:59'
            
            # Get total count
            count_query = query.replace(
                "SELECT audit_id, entity_type, entity_id, entity_name, operation_type, status, started_at, completed_at, duration_ms, user_id, operation_data, error_message, impact_level",
                "SELECT COUNT(*) as total"
            )
            total_result = db.execute_query(count_query, params)
            total = total_result[0]['total'] if total_result and len(total_result) > 0 else 0
            
            # Get paginated results
            query += " ORDER BY started_at DESC LIMIT :limit OFFSET :offset"
            params['limit'] = limit
            params['offset'] = offset
            
            rows = db.execute_query(query, params)
            entries = [dict(row) for row in rows]
            
            return {
                'entries': entries,
                'total': total,
                'page': page,
                'limit': limit,
                'total_pages': (total + limit - 1) // limit
            }
            
        except Exception as e:
            self.log_error("Error getting audit trail", e)
            return {'entries': [], 'total': 0}
    
    async def admin_schedule_alert(
            self,
            alert_id: str,
            schedule_config: Dict[str, Any],
            admin_user_id: str
    ) -> Dict[str, Any]:
        """Admin: Schedule or reschedule an alert"""
        try:
            import json
            
            # Validate schedule config
            required_fields = ['schedule_type', 'schedule_time']
            for field in required_fields:
                if field not in schedule_config:
                    raise ValueError(f"Missing required field: {field}")
            
            # Update alert with schedule config
            query = """
                UPDATE universal_alerts
                SET schedule_config = :schedule_config,
                    updated_at = NOW(),
                    updated_by = :admin_user_id
                WHERE alert_id = :alert_id
            """
            
            params = {
                'alert_id': alert_id,
                'schedule_config': json.dumps(schedule_config),
                'admin_user_id': admin_user_id
            }
            
            result = db.execute_update(query, params)
            
            if result > 0:
                # Log to audit trail
                await self._log_admin_operation(
                    admin_user_id=admin_user_id,
                    operation_type='schedule',
                    entity_type='alert',
                    entity_id=alert_id,
                    operation_data={'schedule_config': schedule_config}
                )
                
                return {'success': True, 'alert_id': alert_id}
            else:
                raise ValueError("Alert not found")
                
        except Exception as e:
            self.log_error("Error scheduling alert", e, {'alert_id': alert_id})
            raise

    async def admin_get_event_type_coverage(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Admin/operator: summarize supported vs observed event types and alert coverage."""
        try:
            supported_by_data_source: Dict[str, List[str]] = {}
            supported_event_types: set[str] = set()
            for name, plugin in (self.plugin_registry.data_source_plugins or {}).items():
                types: List[str] = []
                try:
                    if hasattr(plugin, "get_event_types"):
                        types = list(plugin.get_event_types() or [])
                    elif hasattr(plugin, "supported_event_types"):
                        types = list(getattr(plugin, "supported_event_types") or [])
                except Exception:
                    types = []

                supported_by_data_source[name] = sorted({t for t in types if t})
                supported_event_types.update([t for t in types if t])

            evaluator_event_types = sorted(list((self.plugin_registry.evaluator_plugins or {}).keys()))
            supported_event_types.update(evaluator_event_types)

            observed_query = """
                SELECT
                    event_type,
                    COUNT(*) AS total_count,
                    COUNT(*) FILTER (WHERE processing_status = 'pending') AS pending_count,
                    MAX(COALESCE(detected_at, event_timestamp)) AS last_event_at
                FROM universal_events
                GROUP BY event_type
                ORDER BY event_type
            """
            observed_rows = db.execute_query(observed_query, {})
            observed_by_type: Dict[str, Dict[str, Any]] = {}
            for r in observed_rows or []:
                observed_by_type[str(r.get("event_type") or "")] = dict(r)

            alert_params: Dict[str, Any] = {}
            alerts_where = ""
            if user_id:
                alerts_where = "WHERE user_id = :user_id"
                alert_params["user_id"] = user_id

            alerts_query = f"""
                SELECT
                    alert_type,
                    is_active,
                    COUNT(*) AS count
                FROM universal_alerts
                {alerts_where}
                GROUP BY alert_type, is_active
            """
            alert_rows = db.execute_query(alerts_query, alert_params)
            alerts_by_type: Dict[str, Dict[str, int]] = {}
            for r in alert_rows or []:
                t = str(r.get("alert_type") or "")
                if not t:
                    continue
                if t not in alerts_by_type:
                    alerts_by_type[t] = {"active": 0, "inactive": 0}
                if bool(r.get("is_active")):
                    alerts_by_type[t]["active"] += int(r.get("count") or 0)
                else:
                    alerts_by_type[t]["inactive"] += int(r.get("count") or 0)

            all_types = sorted({t for t in supported_event_types.union(observed_by_type.keys()).union(alerts_by_type.keys()) if t})
            rows: List[Dict[str, Any]] = []
            for t in all_types:
                observed = observed_by_type.get(t, {})
                alerts = alerts_by_type.get(t, {"active": 0, "inactive": 0})
                rows.append({
                    "event_type": t,
                    "supported": t in supported_event_types,
                    "has_evaluator": t in (self.plugin_registry.evaluator_plugins or {}),
                    "supported_by_data_source": [ds for ds, types in supported_by_data_source.items() if t in types],
                    "observed_total": int(observed.get("total_count") or 0),
                    "observed_pending": int(observed.get("pending_count") or 0),
                    "last_event_at": observed.get("last_event_at"),
                    "active_alerts": int(alerts.get("active") or 0),
                    "inactive_alerts": int(alerts.get("inactive") or 0),
                })

            return {
                "supported_event_types": sorted(list(supported_event_types)),
                "evaluator_event_types": evaluator_event_types,
                "data_source_plugins": supported_by_data_source,
                "coverage": rows,
            }
        except Exception as e:
            self.log_error("Error computing event type coverage", e)
            return {
                "supported_event_types": [],
                "evaluator_event_types": [],
                "data_source_plugins": {},
                "coverage": [],
                "error": str(e),
            }
    
    async def admin_get_performance_analytics(
            self,
            days: int = 30,
            alert_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Admin: Get alert performance analytics"""
        try:
            from datetime import datetime, timedelta
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Alert performance metrics
            query = """
                SELECT 
                    alert_type,
                    COUNT(*) as total_alerts,
                    COUNT(*) FILTER (WHERE is_active = true) as active_alerts,
                    SUM(trigger_count) as total_triggers,
                    SUM(success_count) as total_successes,
                    SUM(failure_count) as total_failures,
                    AVG(CASE WHEN trigger_count > 0 
                        THEN (success_count::float / NULLIF(trigger_count, 0)) * 100 
                        ELSE 0 END) as success_rate,
                    MAX(last_triggered_at) as last_trigger
                FROM universal_alerts
                WHERE created_at >= :start_date
            """
            params = {'start_date': start_date}
            
            if alert_type:
                query += " AND alert_type = :alert_type"
                params['alert_type'] = alert_type
            
            query += " GROUP BY alert_type"
            
            rows = db.execute_query(query, params)
            self.log_info(f"Performance analytics query returned {len(rows)} rows")
            
            # Notification performance
            notif_query = """
                SELECT 
                    channel_type,
                    status,
                    COUNT(*) as count,
                    AVG(attempts) as avg_attempts
                FROM universal_notification_queue
                WHERE created_at >= :start_date
                GROUP BY channel_type, status
                ORDER BY channel_type, status
            """
            
            notif_rows = db.execute_query(notif_query, {'start_date': start_date})
            self.log_info(f"Notification query returned {len(notif_rows)} rows")
            
            result = {
                'alert_performance': [dict(row) for row in rows],
                'notification_performance': [dict(row) for row in notif_rows],
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': days
                }
            }
            self.log_info(f"Returning analytics result: {result}")
            return result
            
        except Exception as e:
            self.log_error("Error getting performance analytics", e)
            return {}
    
    async def admin_bulk_action(
            self,
            alert_ids: List[str],
            action: str,
            admin_user_id: str,
            reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """Admin: Bulk action on alerts"""
        try:
            import json
            
            processed = 0
            failed = 0
            results = []
            
            for alert_id in alert_ids:
                try:
                    if action == 'activate':
                        query = "UPDATE universal_alerts SET is_active = true, updated_at = NOW() WHERE alert_id = :alert_id"
                    elif action == 'deactivate':
                        query = "UPDATE universal_alerts SET is_active = false, updated_at = NOW() WHERE alert_id = :alert_id"
                    elif action == 'delete':
                        query = "DELETE FROM universal_alerts WHERE alert_id = :alert_id"
                    else:
                        raise ValueError(f"Invalid action: {action}")
                    
                    result = db.execute_update(query, {'alert_id': alert_id})
                    
                    if result > 0:
                        processed += 1
                        results.append({'alert_id': alert_id, 'status': 'success'})
                        
                        # Log to audit trail
                        await self._log_admin_operation(
                            admin_user_id=admin_user_id,
                            operation_type=action,
                            entity_type='alert',
                            entity_id=alert_id,
                            operation_data={'reason': reason} if reason else {}
                        )
                    else:
                        failed += 1
                        results.append({'alert_id': alert_id, 'status': 'not_found', 'error': 'Alert not found'})
                        
                except Exception as e:
                    failed += 1
                    results.append({'alert_id': alert_id, 'status': 'error', 'error': str(e)})
            
            return {
                'processed': processed,
                'failed': failed,
                'results': results
            }
            
        except Exception as e:
            self.log_error("Error in bulk action", e, {'action': action})
            raise
    
    async def _log_admin_operation(
            self,
            admin_user_id: str,
            operation_type: str,
            entity_type: str,
            entity_id: str,
            operation_data: Dict[str, Any]
    ):
        """Log admin operation to audit trail"""
        try:
            import json
            
            query = """
                INSERT INTO alert_audit_trail (
                    entity_type, entity_id, operation_type, operation_data,
                    status, started_at, completed_at, user_id
                ) VALUES (
                    :entity_type, :entity_id, :operation_type, :operation_data,
                    'completed', NOW(), NOW(), :user_id
                )
            """
            
            params = {
                'entity_type': entity_type,
                'entity_id': entity_id,
                'operation_type': operation_type,
                'operation_data': json.dumps(operation_data),
                'user_id': admin_user_id
            }
            
            db.execute_update(query, params)
            
        except Exception as e:
            self.log_error("Error logging admin operation", e)

    def get_notification_history(self, alert_id: str) -> List[Dict[str, Any]]:
        """Get notification history for a specific alert"""
        try:
            self.log_info(f"Getting notification history for alert: {alert_id}")

            query = """
                SELECT
                    nq.queue_id,
                    e.alert_id,
                    nq.alert_event_id,
                    nq.channel_type,
                    nq.recipient,
                    nq.subject,
                    nq.message_body,
                    nq.status,
                    nq.created_at
                FROM universal_notification_queue nq
                JOIN universal_alert_events e
                  ON e.event_id = nq.alert_event_id
                WHERE e.alert_id = :alert_id
                ORDER BY nq.created_at DESC
                LIMIT 200
            """

            results = db.execute_query(query, {'alert_id': alert_id})

            notifications: List[Dict[str, Any]] = []
            for row in results or []:
                created_at = row.get('created_at')
                notifications.append({
                    'notification_id': str(row.get('queue_id') or ''),
                    'alert_id': str(row.get('alert_id') or alert_id),
                    'alert_event_id': str(row.get('alert_event_id') or ''),
                    'channel': row.get('channel_type'),
                    'recipient': row.get('recipient'),
                    'subject': row.get('subject'),
                    'message': row.get('message_body'),
                    'status': row.get('status'),
                    'created_at': created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at),
                })

            self.log_info(f"Found {len(notifications)} notification queue records for alert {alert_id}")
            return notifications
            
        except Exception as e:
            self.log_error(f"Error getting notification history for alert {alert_id}", e)
            return []

    def delete_notification_history(self, alert_id: str) -> int:
        """Delete notification queue records for a specific alert"""
        try:
            query = """
                DELETE FROM universal_notification_queue nq
                USING universal_alert_events e
                WHERE e.event_id = nq.alert_event_id
                  AND e.alert_id = :alert_id
            """
            return int(db.execute_update(query, {"alert_id": alert_id}) or 0)
        except Exception as e:
            self.log_error(f"Error deleting notification history for alert {alert_id}", e)
            return 0

    def clear_notifications_for_user(self, user_id: str) -> int:
        """Delete notification queue records for all alerts belonging to a user"""
        try:
            query = """
                DELETE FROM universal_notification_queue nq
                USING universal_alert_events e, universal_alerts a
                WHERE e.event_id = nq.alert_event_id
                  AND a.alert_id = e.alert_id
                  AND a.user_id = :user_id
            """
            return int(db.execute_update(query, {"user_id": user_id}) or 0)
        except Exception as e:
            self.log_error(f"Error clearing notifications for user {user_id}", e)
            return 0

# Global service instance
universal_alert_service = UniversalAlertServiceEnhanced()
