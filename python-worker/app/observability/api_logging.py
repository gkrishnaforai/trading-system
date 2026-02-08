"""
API Request/Response Logging Middleware
Comprehensive logging for all API calls with tracking IDs and correlation
"""

import time
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.logging import get_logger, log_with_context
from app.observability.constants import generate_tracking_id, PERFORMANCE_THRESHOLDS

logger = get_logger("api_middleware")

class APILoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all API requests and responses with comprehensive tracking
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique tracking ID for this request
        tracking_id = generate_tracking_id("api")
        
        # Start timing
        start_time = time.time()
        
        # Extract request information
        method = request.method
        url = str(request.url)
        path = request.url.path
        query_params = dict(request.query_params)
        
        # Log request start
        log_with_context(
            logger,
            20,  # INFO level
            f"🌐 API Request Started",
            {
                "tracking_id": tracking_id,
                "method": method,
                "path": path,
                "full_url": url,
                "query_params": query_params,
                "client_ip": self._get_client_ip(request),
                "user_agent": request.headers.get("user-agent", "Unknown")
            },
            correlation_id=tracking_id
        )
        
        # Try to get request body for POST/PUT/PATCH requests
        request_body = None
        if method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    # Log body size and type, not content for security
                    request_body = {
                        "size_bytes": len(body),
                        "content_type": request.headers.get("content-type", "Unknown"),
                        "has_json": "application/json" in request.headers.get("content-type", "")
                    }
            except Exception as e:
                logger.warning(f"Failed to read request body: {e}")
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            processing_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Extract response information
            status_code = response.status_code
            response_size = len(response.body) if hasattr(response, 'body') else 0
            
            # Log response
            log_with_context(
                logger,
                20 if status_code < 400 else 40,  # INFO for success, ERROR for failures
                f"🌐 API Request Completed",
                {
                    "tracking_id": tracking_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "processing_time_ms": round(processing_time, 2),
                    "response_size_bytes": response_size,
                    "success": status_code < 400
                },
                correlation_id=tracking_id
            )
            
            # Add tracking ID to response headers
            response.headers["X-Tracking-ID"] = tracking_id
            response.headers["X-Processing-Time"] = f"{processing_time:.2f}ms"
            
            return response
            
        except Exception as e:
            # Calculate processing time for failed request
            processing_time = (time.time() - start_time) * 1000
            
            # Log error
            log_with_context(
                logger,
                40,  # ERROR level
                f"💥 API Request Failed",
                {
                    "tracking_id": tracking_id,
                    "method": method,
                    "path": path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "processing_time_ms": round(processing_time, 2),
                    "request_body": request_body
                },
                correlation_id=tracking_id,
                exc_info=e
            )
            
            # Return error response
            error_response = {
                "success": False,
                "error": str(e),
                "tracking_id": tracking_id,
                "processing_time_ms": round(processing_time, 2)
            }
            
            return JSONResponse(
                status_code=500,
                content=error_response,
                headers={
                    "X-Tracking-ID": tracking_id,
                    "X-Processing-Time": f"{processing_time:.2f}ms"
                }
            )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check for forwarded IP
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        
        # Fall back to client IP
        return request.client.host if request.client else "Unknown"


class APIPerformanceLogger:
    """
    Utility class for logging API performance metrics
    """
    
    @staticmethod
    def log_slow_request(tracking_id: str, method: str, path: str, processing_time: float, threshold: float = None):
        """Log slow requests"""
        threshold = threshold or PERFORMANCE_THRESHOLDS["slow_request_ms"]
        if processing_time > threshold:
            log_with_context(
                logger,
                30,  # WARNING level
                f"⚠️ Slow API Request Detected",
                {
                    "tracking_id": tracking_id,
                    "method": method,
                    "path": path,
                    "processing_time_ms": round(processing_time, 2),
                    "threshold_ms": threshold,
                    "slow_by_ms": round(processing_time - threshold, 2)
                },
                correlation_id=tracking_id
            )
    
    @staticmethod
    def log_error_response(tracking_id: str, method: str, path: str, status_code: int, error: str = None):
        """Log error responses"""
        log_with_context(
            logger,
            40,  # ERROR level
            f"❌ API Error Response",
            {
                "tracking_id": tracking_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "error": error,
                "is_client_error": 400 <= status_code < 500,
                "is_server_error": status_code >= 500
            },
            correlation_id=tracking_id
        )
    
    @staticmethod
    def log_health_check(tracking_id: str, processing_time: float, status: str):
        """Log health check requests"""
        log_with_context(
            logger,
            20,  # INFO level
            f"💓 Health Check",
            {
                "tracking_id": tracking_id,
                "processing_time_ms": round(processing_time, 2),
                "status": status
            },
            correlation_id=tracking_id
        )
