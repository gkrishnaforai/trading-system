"""
Event System for Trading System
Industry Standard: Observer Pattern / Event-Driven Architecture
Supports: Agent workflows, real-time updates, workflow triggers
"""
from app.events.manager import EventManager, get_event_manager
from app.events.types import EventType, TradingEvent

__all__ = [
    'EventManager',
    'get_event_manager',
    'EventType',
    'TradingEvent',
]

