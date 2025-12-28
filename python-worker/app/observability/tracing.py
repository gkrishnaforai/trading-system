"""
Distributed Tracing
SOLID: Single responsibility for operation tracing
DRY: Centralized tracing utilities
Performance: Minimal overhead tracing
"""
from typing import Any, Callable, Optional
from functools import wraps
import time

from app.observability.logging import get_logger


def trace_function(operation_name: str):
    """
    Decorator for tracing function execution
    DRY: Centralized tracing logic
    Performance: Lightweight timing and logging
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = get_logger("tracing")
            start_time = time.time()
            
            try:
                logger.debug(f"Starting {operation_name}")
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                logger.debug(
                    f"Completed {operation_name} in {duration:.3f}s",
                    extra={
                        "operation": operation_name,
                        "duration": duration,
                        "status": "success"
                    }
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                logger.error(
                    f"Failed {operation_name} after {duration:.3f}s: {str(e)}",
                    extra={
                        "operation": operation_name,
                        "duration": duration,
                        "status": "error",
                        "error": str(e)
                    }
                )
                
                raise
                
        return wrapper
    return decorator


class TraceContext:
    """Context manager for tracing operations"""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.logger = get_logger("tracing")
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type is None:
            self.logger.debug(
                f"Completed {self.operation_name} in {duration:.3f}s",
                extra={"operation": self.operation_name, "duration": duration, "status": "success"}
            )
        else:
            self.logger.error(
                f"Failed {self.operation_name} after {duration:.3f}s: {exc_val}",
                extra={"operation": self.operation_name, "duration": duration, "status": "error", "error": str(exc_val)}
            )
