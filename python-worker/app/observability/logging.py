"""
Enhanced structured logging with robust exception handling
Industry standard: JSON logging for production, human-readable for development
"""
import logging
import json
import sys
import traceback
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import os

from app.config import settings


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, exception: Exception, context: str = "") -> None:
    """
    Industry Standard: Log detailed exception information with context
    Provides root cause analysis and full traceback for debugging
    """
    exc_type, exc_value, exc_traceback = sys.exc_info()
    root_exc = _get_root_exception(exception)
    root_origin = _get_exception_origin(root_exc)
    
    # Create comprehensive exception data
    exception_data = {
        'timestamp': datetime.now().isoformat(),
        'context': context,
        'exception_type': exc_type.__name__ if exc_type else 'Unknown',
        'exception_message': str(exception),
        'exception_module': getattr(exception, '__module__', 'Unknown'),
        'root_cause': _extract_root_cause(exception),
        'root_cause_exception_type': type(root_exc).__name__,
        'root_cause_exception_message': str(root_exc),
        'root_cause_origin': {
            'file': root_origin[0],
            'line': root_origin[1],
            'function': root_origin[2],
        },
        'traceback': traceback.format_exception(exc_type, exc_value, exc_traceback),
        'system_info': {
            'python_version': sys.version,
            'platform': sys.platform
        }
    }
    
    # Log structured exception data
    logger.error(f"🚨 EXCEPTION DETECTED: {context}")
    logger.error(f"   Type: {exception_data['exception_type']}")
    logger.error(f"   Message: {exception_data['exception_message']}")
    logger.error(f"   Root Cause: {exception_data['root_cause']}")
    logger.error(f"   Module: {exception_data['exception_module']}")
    logger.error(
        "   Root Cause Origin: %s:%s in %s()",
        exception_data['root_cause_origin']['file'],
        exception_data['root_cause_origin']['line'],
        exception_data['root_cause_origin']['function'],
    )
    
    # Log full traceback in debug mode
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Full traceback:")
        for line in exception_data['traceback']:
            logger.debug(f"   {line.rstrip()}")
    return exception_data


def _get_root_exception(exception: Exception) -> Exception:
    """Return the deepest exception in a chained raise-from/context stack."""
    current: Exception = exception
    visited = set()
    while True:
        current_id = id(current)
        if current_id in visited:
            return current
        visited.add(current_id)
 
        if getattr(current, '__cause__', None) is not None:
            current = current.__cause__  # type: ignore[assignment]
            continue
        if getattr(current, '__context__', None) is not None:
            current = current.__context__  # type: ignore[assignment]
            continue
        return current


def _get_exception_origin(exception: Exception) -> Tuple[str, int, str]:
    """Best-effort origin extraction: last frame of the exception traceback."""
    tb = exception.__traceback__
    if tb is None:
        return ("Unknown", 0, "Unknown")
    frames = traceback.extract_tb(tb)
    if not frames:
        return ("Unknown", 0, "Unknown")
    last = frames[-1]
    return (last.filename, last.lineno, last.name)


def _extract_root_cause(exception: Exception) -> str:
    """
    Extract meaningful root cause from exception
    Industry standard error analysis
    """
    error_message = str(exception).lower()
    
    # Database errors
    if 'duplicate key' in error_message:
        return "Database constraint violation - duplicate record"
    elif 'connection' in error_message:
        return "Database connection error"
    elif 'timeout' in error_message:
        return "Database operation timeout"
    elif 'transaction' in error_message and 'abort' in error_message:
        return "Database transaction aborted - previous error not handled"
    elif 'invalid input syntax' in error_message:
        return "Data type conversion error"
    
    # Network/API errors
    elif 'timeout' in error_message:
        return "Network timeout"
    elif 'connection' in error_message:
        return "Network connection error"
    elif 'rate limit' in error_message:
        return "API rate limit exceeded"
    
    # Data errors
    elif 'value' in error_message or 'type' in error_message:
        return "Data type conversion error"
    elif 'index' in error_message and 'out of range' in error_message:
        return "Array/index access error"
    elif 'key' in error_message and 'not found' in error_message:
        return "Missing data key"
    
    # File system errors
    elif 'no such file' in error_message:
        return "File not found"
    elif 'permission' in error_message:
        return "File permission error"
    
    # Default
    return f"Unknown error: {str(exception)[:100]}"


def log_operation_start(logger: logging.Logger, operation: str, details: Dict[str, Any] = None) -> str:
    """
    Log operation start with tracking ID
    Industry standard operation tracking
    """
    tracking_id = f"{operation}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(str(details)) % 10000:04d}"
    
    logger.info(f"🚀 STARTING: {operation}")
    logger.info(f"   Tracking ID: {tracking_id}")
    if details:
        for key, value in details.items():
            logger.info(f"   {key}: {value}")
    
    return tracking_id


def log_operation_success(logger: logging.Logger, operation: str, tracking_id: str, results: Dict[str, Any] = None) -> None:
    """
    Log successful operation completion
    """
    logger.info(f"✅ COMPLETED: {operation}")
    logger.info(f"   Tracking ID: {tracking_id}")
    if results:
        for key, value in results.items():
            logger.info(f"   {key}: {value}")


def log_operation_failure(logger: logging.Logger, operation: str, tracking_id: str, exception: Exception) -> None:
    """
    Log failed operation with detailed exception info
    """
    logger.error(f"❌ FAILED: {operation}")
    logger.error(f"   Tracking ID: {tracking_id}")
    log_exception(logger, exception, f"Operation: {operation}")


def log_config():
    """Log configuration on startup, masking sensitive values."""
    logger = get_logger(__name__)
    sensitive_keys = {"api_key", "secret", "token", "password", "key"}
    config_dict = settings.model_dump()

    logger.info("=== Configuration ===")
    for key, value in config_dict.items():
        if any(s in key.lower() for s in sensitive_keys):
            masked = "********" if value else None
            logger.info(f"{key}: {masked}")
        else:
            logger.info(f"{key}: {value}")
    logger.info("====================")


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging
    Industry standard: Machine-readable logs for aggregation and analysis
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra context if present
        if hasattr(record, 'context') and record.context:
            log_data['context'] = record.context
        
        # Add correlation ID if present
        if hasattr(record, 'correlation_id') and record.correlation_id:
            log_data['correlation_id'] = record.correlation_id
        
        return json.dumps(log_data)


def setup_logging():
    """
    Setup logging configuration
    Development: Human-readable format
    Production: JSON structured format
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    is_production = settings.environment.lower() == 'production'
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    
    # Use structured formatter in production, standard formatter in development
    if is_production:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    logging.info(f"✅ Logging configured (level: {log_level}, format: {'JSON' if is_production else 'human-readable'})")


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance with context support
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
    exc_info: Optional[Exception] = None
):
    """
    Log with structured context
    
    Args:
        logger: Logger instance
        level: Log level (logging.INFO, logging.ERROR, etc.)
        message: Log message
        context: Additional context dictionary
        correlation_id: Correlation ID for request tracing
        exc_info: Exception info for error logging
    """
    extra = {}
    if context:
        extra['context'] = context
    if correlation_id:
        extra['correlation_id'] = correlation_id
    
    logger.log(level, message, extra=extra, exc_info=exc_info)

