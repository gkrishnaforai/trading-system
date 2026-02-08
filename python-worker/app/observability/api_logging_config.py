"""
Enhanced Logging Configuration for Universal Alert API
Comprehensive logging setup for development and production
"""

import logging
import sys
from typing import Dict, Any

from app.observability.logging import setup_logging, get_logger
from app.observability.api_logging import APILoggingMiddleware, APIPerformanceLogger
from app.observability.constants import (
    ENVIRONMENT_LOG_LEVELS, 
    API_ENDPOINT_CONFIG, 
    DEFAULT_LOG_PATHS,
    PERFORMANCE_THRESHOLDS,
    ERROR_RATE_THRESHOLDS
)

# Configure enhanced logging for the Universal Alert API
def setup_universal_alert_logging(environment: str = "development"):
    """Setup comprehensive logging for the Universal Alert API"""
    
    # Setup base logging
    setup_logging()
    
    # Get the universal alert API logger
    api_logger = get_logger("universal_alert_api")
    middleware_logger = get_logger("api_middleware")
    
    # Set specific log levels for different components based on environment
    env_levels = ENVIRONMENT_LOG_LEVELS.get(environment, ENVIRONMENT_LOG_LEVELS["development"])
    
    for component, level in env_levels.items():
        log_level = getattr(logging, level.upper(), logging.INFO)
        logging.getLogger(component).setLevel(log_level)
    
    # Create console handler with detailed format for development
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Enhanced formatter for API calls
    api_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s | %(funcName)s:%(lineno)d'
    )
    console_handler.setFormatter(api_formatter)
    
    # Add handler to API loggers
    api_logger.addHandler(console_handler)
    middleware_logger.addHandler(console_handler)
    
    # Log startup
    api_logger.info("=" * 80)
    api_logger.info("🚀 Universal Alert API Logging Initialized")
    api_logger.info("=" * 80)
    api_logger.info(f"📊 Environment: {environment}")
    api_logger.info("📊 Log Levels:")
    for component, level in env_levels.items():
        api_logger.info(f"   • {component}: {level}")
    api_logger.info("=" * 80)
    
    return api_logger, middleware_logger

def get_endpoint_config(method: str, path: str) -> Dict[str, Any]:
    """Get logging configuration for an endpoint"""
    # Normalize path (replace {param} with actual values)
    normalized_path = path
    if "/alerts/" in path and method in ["PUT", "DELETE"]:
        normalized_path = f"{method} /alerts/{{alert_id}}"
    
    endpoint_key = f"{method} {normalized_path}"
    return API_ENDPOINT_CONFIG.get(endpoint_key, {
        "log_level": "INFO",
        "log_request_body": method in ["POST", "PUT"],
        "log_response_body": True,
        "log_performance": True,
        "slow_request_threshold": PERFORMANCE_THRESHOLDS["slow_request_ms"]
    })

# Create a comprehensive API call logger
class APICallLogger:
    """Enhanced API call logger with detailed tracking"""
    
    def __init__(self):
        self.logger = get_logger("api_calls")
        self.performance_logger = APIPerformanceLogger()
    
    def log_request_start(self, tracking_id: str, method: str, path: str, 
                         user_id: str = None, request_data: Dict[str, Any] = None):
        """Log the start of an API call"""
        config = get_endpoint_config(method, path)
        
        log_data = {
            "tracking_id": tracking_id,
            "method": method,
            "path": path,
            "user_id": user_id,
            "endpoint_config": config
        }
        
        if request_data and config.get("log_request_body"):
            # Log request data size and type, not content for security
            log_data["request_info"] = {
                "data_keys": list(request_data.keys()) if isinstance(request_data, dict) else "non_dict",
                "data_size": len(str(request_data))
            }
        
        self.logger.info(f"🚀 API Call Started: {method} {path}", extra=log_data)
    
    def log_request_success(self, tracking_id: str, method: str, path: str,
                           response_data: Dict[str, Any] = None, processing_time: float = None):
        """Log successful API call completion"""
        config = get_endpoint_config(method, path)
        
        log_data = {
            "tracking_id": tracking_id,
            "method": method,
            "path": path,
            "success": True
        }
        
        if processing_time is not None:
            log_data["processing_time_ms"] = round(processing_time, 2)
            
            # Check for slow requests
            if processing_time > config.get("slow_request_threshold", 1000.0):
                self.performance_logger.log_slow_request(
                    tracking_id, method, path, processing_time, 
                    config.get("slow_request_threshold", 1000.0)
                )
        
        if response_data and config.get("log_response_body"):
            # Log response summary
            log_data["response_summary"] = {
                "success": response_data.get("success", False),
                "has_data": "data" in response_data or "alerts" in response_data,
                "response_size": len(str(response_data))
            }
        
        self.logger.info(f"✅ API Call Completed: {method} {path}", extra=log_data)
    
    def log_request_error(self, tracking_id: str, method: str, path: str,
                          error: str, error_type: str = None, processing_time: float = None):
        """Log failed API call"""
        config = get_endpoint_config(method, path)
        
        log_data = {
            "tracking_id": tracking_id,
            "method": method,
            "path": path,
            "success": False,
            "error": error,
            "error_type": error_type
        }
        
        if processing_time is not None:
            log_data["processing_time_ms"] = round(processing_time, 2)
        
        self.logger.error(f"❌ API Call Failed: {method} {path}", extra=log_data)
        
        # Also log as performance error
        self.performance_logger.log_error_response(tracking_id, method, path, 500, error)

# Global API call logger instance
api_call_logger = APICallLogger()
