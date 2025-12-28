"""
Event Types for Trading System
Industry Standard: Event-Driven Architecture
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum


class EventType(Enum):
    """Types of events in the system"""
    # Data events
    DATA_FETCHED = "data_fetched"
    DATA_REFRESHED = "data_refreshed"
    INDICATORS_CALCULATED = "indicators_calculated"
    
    # Signal events
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_UPDATED = "signal_updated"
    
    # Agent events
    AGENT_TASK_STARTED = "agent_task_started"
    AGENT_TASK_COMPLETED = "agent_task_completed"
    AGENT_TASK_FAILED = "agent_task_failed"
    
    # Workflow events
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    
    # Portfolio events
    PORTFOLIO_UPDATED = "portfolio_updated"
    POSITION_ADDED = "position_added"
    POSITION_REMOVED = "position_removed"
    
    # User events
    USER_ACTION = "user_action"
    SUBSCRIPTION_CHANGED = "subscription_changed"


@dataclass
class TradingEvent:
    """Base event class for trading system events"""
    event_type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    source: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

