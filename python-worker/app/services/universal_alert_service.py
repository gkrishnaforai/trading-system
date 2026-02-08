"""Compatibility shim.

This project uses `universal_alert_service_enhanced` as the single source of truth.
We keep this module to avoid breaking any legacy imports.
"""

from app.services.universal_alert_service_enhanced import (  # noqa: F401
    AlertDefinition,
    AlertStatus,
    EntityType,
    EventStatus,
    UniversalAlertService,
    UniversalEvent,
    UrgencyLevel,
    universal_alert_service,
)
