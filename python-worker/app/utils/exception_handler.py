"""
Exception Handling Decorator
DRY: Standardizes exception handling patterns across the codebase
"""
import logging
from functools import wraps
from typing import Callable, Any, Optional, Type
from inspect import signature

from app.exceptions import TradingSystemError, DatabaseError, ValidationError

logger = logging.getLogger(__name__)


def handle_exceptions(
    default_exception: Type[TradingSystemError] = TradingSystemError,
    log_error: bool = True,
    reraise: bool = True,
    context_keys: Optional[list] = None
):
    """
    Decorator for standardizing exception handling
    
    Args:
        default_exception: Exception type to raise if generic Exception is caught
        log_error: Whether to log errors
        reraise: Whether to re-raise exceptions (True for fail-fast)
        context_keys: List of parameter names to include in error context
    
    Usage:
        @handle_exceptions(default_exception=DatabaseError, context_keys=['symbol'])
        def get_stock_data(symbol: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build context from function parameters
            context = {}
            if context_keys:
                sig = signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                
                for key in context_keys:
                    if key in bound_args.arguments:
                        context[key] = bound_args.arguments[key]
            
            try:
                return func(*args, **kwargs)
            
            # Re-raise TradingSystemError exceptions (they're already properly formatted)
            except TradingSystemError:
                if reraise:
                    raise
                return None
            
            # Handle specific exceptions
            except (ValueError, TypeError, KeyError) as e:
                error_msg = f"Invalid input in {func.__name__}: {str(e)}"
                if log_error:
                    logger.error(error_msg, exc_info=True, extra={'context': context})
                
                if reraise:
                    raise ValidationError(error_msg, details=context) from e
                return None
            
            # Handle database errors
            except Exception as e:
                error_msg = f"Error in {func.__name__}: {str(e)}"
                if log_error:
                    logger.error(error_msg, exc_info=True, extra={'context': context})
                
                if reraise:
                    raise default_exception(error_msg, details=context) from e
                return None
        
        return wrapper
    return decorator


def handle_database_errors(func: Callable) -> Callable:
    """
    Decorator specifically for database operations
    Automatically converts exceptions to DatabaseError with context
    
    Usage:
        @handle_database_errors
        def save_data(symbol: str, data: dict):
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DatabaseError:
            raise  # Re-raise DatabaseError as-is
        except Exception as e:
            # Extract symbol from args/kwargs if available
            context = {}
            if args and isinstance(args[0], str):
                context['symbol'] = args[0]
            if 'symbol' in kwargs:
                context['symbol'] = kwargs['symbol']
            
            error_msg = f"Database error in {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True, extra={'context': context})
            raise DatabaseError(error_msg, details=context) from e
    
    return wrapper


def handle_validation_errors(func: Callable) -> Callable:
    """
    Decorator specifically for validation operations
    Automatically converts exceptions to ValidationError
    
    Usage:
        @handle_validation_errors
        def validate_input(symbol: str):
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError:
            raise  # Re-raise ValidationError as-is
        except (ValueError, TypeError, KeyError) as e:
            context = {}
            if args and isinstance(args[0], str):
                context['input'] = args[0]
            
            error_msg = f"Validation error in {func.__name__}: {str(e)}"
            logger.warning(error_msg, extra={'context': context})
            raise ValidationError(error_msg, details=context) from e
    
    return wrapper

