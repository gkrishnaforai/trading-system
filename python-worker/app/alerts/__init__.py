"""
Pluggable Alert System
Industry Standard: Plugin-based alert system with extensible architecture
Supports: Email, SMS, Push, Webhook notifications
New alert types can be added via configuration or database without code changes
"""
from app.alerts.base import BaseAlertPlugin, AlertMetadata, AlertContext, AlertResult
from app.alerts.registry import AlertRegistry, get_alert_registry
from app.alerts.service import AlertService

__all__ = [
    'BaseAlertPlugin',
    'AlertMetadata',
    'AlertContext',
    'AlertResult',
    'AlertRegistry',
    'get_alert_registry',
    'AlertService',
]

