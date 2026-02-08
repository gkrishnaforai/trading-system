"""
Shared constants and utilities for observability components
DRY - Don't Repeat Yourself
"""

from typing import Dict, Any
from datetime import datetime
import uuid
import time

# Tracking ID generation
def generate_tracking_id(operation: str = "api") -> str:
    """Generate a unique tracking ID for operations"""
    timestamp = int(time.time())
    unique_id = uuid.uuid4().hex[:8]
    return f"{operation}_{timestamp}_{unique_id}"

# Common log patterns
LOG_PATTERNS = {
    "request_start": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+) \| (\w+) \| 🚀 API Call Started: (\w+) (.+)",
    "request_success": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+) \| (\w+) \| ✅ API Call Completed: (\w+) (.+)",
    "request_error": r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) \| (\w+) \| (\w+) \| ❌ API Call Failed: (\w+) (.+)",
    "operation_start": r"🚀 STARTING: (\w+)",
    "operation_success": r"✅ COMPLETED: (\w+)",
    "operation_failure": r"❌ FAILED: (\w+)",
    "tracking_id": r"tracking_id[_\s:]+(\w+)",
    "user_id": r"user_id[_\s:]+([a-f0-9-]+)",
    "alert_id": r"alert_id[_\s:]+([a-f0-9-]+)"
}

# API endpoint configurations
API_ENDPOINT_CONFIG = {
    "POST /alerts": {
        "log_level": "INFO",
        "log_request_body": True,
        "log_response_body": True,
        "log_performance": True,
        "slow_request_threshold": 1000.0  # ms
    },
    "GET /alerts": {
        "log_level": "INFO",
        "log_request_body": False,
        "log_response_body": True,
        "log_performance": True,
        "slow_request_threshold": 500.0   # ms
    },
    "PUT /alerts/{alert_id}": {
        "log_level": "INFO",
        "log_request_body": True,
        "log_response_body": True,
        "log_performance": True,
        "slow_request_threshold": 1000.0  # ms
    },
    "DELETE /alerts/{alert_id}": {
        "log_level": "INFO",
        "log_request_body": False,
        "log_response_body": True,
        "log_performance": True,
        "slow_request_threshold": 500.0   # ms
    },
    "GET /health": {
        "log_level": "DEBUG",
        "log_request_body": False,
        "log_response_body": False,
        "log_performance": True,
        "slow_request_threshold": 100.0   # ms
    }
}

# Log levels by environment
ENVIRONMENT_LOG_LEVELS = {
    "development": {
        "universal_alert_api": "DEBUG",
        "api_middleware": "DEBUG",
        "universal_alert_service": "DEBUG",
        "DataRefreshManager": "DEBUG",  # Added for detailed logging
        "database": "DEBUG",  # Changed to DEBUG for development
        "external_apis": "DEBUG"
    },
    "production": {
        "universal_alert_api": "INFO",
        "api_middleware": "INFO",
        "universal_alert_service": "INFO",
        "DataRefreshManager": "INFO",  # INFO in production
        "database": "WARNING",
        "external_apis": "WARNING"
    },
    "testing": {
        "universal_alert_api": "WARNING",
        "api_middleware": "WARNING",
        "universal_alert_service": "WARNING",
        "DataRefreshManager": "WARNING",  # WARNING in testing
        "database": "ERROR",
        "external_apis": "WARNING"
    },
}

# Default log file paths
DEFAULT_LOG_PATHS = {
    "api": "logs/universal_alert_api.log",
    "service": "logs/universal_alert_service.log",
    "database": "logs/database.log",
    "audit": "logs/audit.log"
}

# Performance thresholds
PERFORMANCE_THRESHOLDS = {
    "slow_request_ms": 1000.0,
    "very_slow_request_ms": 5000.0,
    "health_check_ms": 100.0,
    "simple_query_ms": 500.0,
    "complex_query_ms": 2000.0
}

# Error rate thresholds for alerting
ERROR_RATE_THRESHOLDS = {
    "warning": 5.0,    # 5%
    "critical": 10.0,  # 10%
    "emergency": 25.0  # 25%
}

# Audit actions
AUDIT_ACTIONS = {
    "alert_created": "Create new alert",
    "alert_updated": "Update existing alert", 
    "alert_deleted": "Delete alert",
    "alert_triggered": "Alert was triggered",
    "user_login": "User logged in",
    "user_logout": "User logged out",
    "config_changed": "Configuration changed"
}

# Common validation functions
def validate_user_id(user_id: str) -> bool:
    """Validate user ID format"""
    return len(user_id) == 36 and user_id.count('-') == 4

def validate_alert_id(alert_id: str) -> bool:
    """Validate alert ID format"""
    return len(alert_id) == 36 and alert_id.count('-') == 4

def validate_tracking_id(tracking_id: str) -> bool:
    """Validate tracking ID format"""
    parts = tracking_id.split('_')
    return len(parts) >= 3 and parts[0].isalnum() and parts[1].isdigit() and len(parts[2]) == 8

# Utility functions
def format_timestamp(timestamp: datetime) -> str:
    """Format timestamp consistently"""
    return timestamp.strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]

def truncate_id(id_str: str, length: int = 8) -> str:
    """Truncate ID for display"""
    return f"{id_str[:length]}..." if len(id_str) > length else id_str

def safe_get_dict_value(d: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely get value from dictionary with default"""
    return d.get(key, default) if isinstance(d, dict) else default
