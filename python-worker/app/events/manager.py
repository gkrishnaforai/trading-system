"""
Event Manager
Industry Standard: Observer Pattern / Pub-Sub Pattern
Manages event publishing and subscription for agent workflows
"""
import logging
from typing import Dict, Any, Optional, List, Callable
from collections import defaultdict

from app.events.types import EventType, TradingEvent

logger = logging.getLogger(__name__)


class EventManager:
    """
    Manages events for the trading system
    Supports: Event publishing, subscription, filtering
    Used by: AI agents, workflows, real-time updates
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._event_history: List[TradingEvent] = []
        self._max_history = 1000  # Keep last 1000 events
    
    def subscribe(
        self,
        event_type: EventType,
        callback: Callable[[TradingEvent], None],
        filter_func: Optional[Callable[[TradingEvent], bool]] = None
    ) -> str:
        """
        Subscribe to events
        
        Args:
            event_type: Type of event to subscribe to
            callback: Callback function to call when event occurs
            filter_func: Optional filter function to filter events
        
        Returns:
            Subscription ID
        """
        subscription_id = f"{event_type.value}_{id(callback)}"
        
        # Wrap callback with filter if provided
        if filter_func:
            def filtered_callback(event: TradingEvent):
                if filter_func(event):
                    callback(event)
            self._subscribers[event_type].append(filtered_callback)
        else:
            self._subscribers[event_type].append(callback)
        
        logger.debug(f"✅ Subscribed to {event_type.value}: {subscription_id}")
        return subscription_id
    
    def publish(self, event: TradingEvent) -> None:
        """
        Publish an event
        
        Args:
            event: Event to publish
        """
        # Add to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # Notify subscribers
        subscribers = self._subscribers.get(event.event_type, [])
        for callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.error(
                    f"Error in event callback for {event.event_type.value}: {e}",
                    exc_info=True
                )
        
        logger.debug(f"📢 Published event: {event.event_type.value}")
    
    def publish_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> TradingEvent:
        """
        Convenience method to create and publish an event
        
        Args:
            event_type: Type of event
            data: Event data
            source: Event source
            correlation_id: Correlation ID for tracing
        
        Returns:
            Created event
        """
        event = TradingEvent(
            event_type=event_type,
            timestamp=None,  # Will be set in __post_init__
            data=data,
            source=source,
            correlation_id=correlation_id
        )
        self.publish(event)
        return event
    
    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> List[TradingEvent]:
        """
        Get event history
        
        Args:
            event_type: Filter by event type (optional)
            limit: Maximum number of events to return
        
        Returns:
            List of events
        """
        events = self._event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        return events[-limit:]
    
    def unsubscribe(self, event_type: EventType, callback: Callable) -> bool:
        """
        Unsubscribe from events
        
        Args:
            event_type: Type of event
            callback: Callback function to remove
        
        Returns:
            True if unsubscribed
        """
        if callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            logger.debug(f"✅ Unsubscribed from {event_type.value}")
            return True
        return False


# Global event manager instance
_event_manager: Optional[EventManager] = None


def get_event_manager() -> EventManager:
    """Get global event manager instance"""
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
    return _event_manager

