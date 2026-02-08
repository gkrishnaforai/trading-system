"""
Observability Module for Universal Alert System
Comprehensive logging, metrics, tracing, and audit functionality
"""

# Core logging functionality
from .logging import (
    get_logger,
    setup_logging,
    log_exception,
    log_operation_start,
    log_operation_success,
    log_operation_failure,
    log_with_context,
    StructuredFormatter
)

# Metrics and monitoring
from .metrics import get_metrics, MetricsCollector, track_duration

# Tracing and context
from .context import get_ingestion_run_id, set_ingestion_run_id

# Audit functionality
from .audit_logger import audit_log, AuditLogger, audit_logger

# API logging middleware
from .api_logging import APILoggingMiddleware, APIPerformanceLogger

# Configuration and utilities
from .constants import (
    generate_tracking_id,
    LOG_PATTERNS,
    API_ENDPOINT_CONFIG,
    ENVIRONMENT_LOG_LEVELS,
    DEFAULT_LOG_PATHS,
    PERFORMANCE_THRESHOLDS,
    ERROR_RATE_THRESHOLDS,
    AUDIT_ACTIONS,
    validate_user_id,
    validate_alert_id,
    validate_tracking_id,
    format_timestamp,
    truncate_id
)

# Log viewing utilities
from .log_viewer import APILogViewer, log_viewer
from .api_logging_config import setup_universal_alert_logging, get_endpoint_config

# Legacy imports for compatibility
from . import audit

__all__ = [
    # Core logging
    "get_logger",
    "setup_logging", 
    "log_exception",
    "log_operation_start",
    "log_operation_success",
    "log_operation_failure",
    "log_with_context",
    "StructuredFormatter",
    
    # Metrics
    "get_metrics",
    "MetricsCollector",
    "track_duration",
    
    # Context
    "get_ingestion_run_id",
    "set_ingestion_run_id",
    
    # Audit
    "audit_log",
    "AuditLogger",
    "audit_logger",
    
    # API middleware
    "APILoggingMiddleware",
    "APIPerformanceLogger",
    
    # Configuration
    "generate_tracking_id",
    "LOG_PATTERNS",
    "API_ENDPOINT_CONFIG",
    "ENVIRONMENT_LOG_LEVELS",
    "DEFAULT_LOG_PATHS",
    "PERFORMANCE_THRESHOLDS",
    "ERROR_RATE_THRESHOLDS",
    "AUDIT_ACTIONS",
    "validate_user_id",
    "validate_alert_id", 
    "validate_tracking_id",
    "format_timestamp",
    "truncate_id",
    
    # Log viewing
    "APILogViewer",
    "log_viewer",
    "setup_universal_alert_logging",
    "get_endpoint_config",
    
    # Legacy compatibility
    "audit"
]
