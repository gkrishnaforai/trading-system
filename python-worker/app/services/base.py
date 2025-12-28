"""
Base service interface
SOLID: Dependency Inversion Principle - depend on abstractions
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseService(ABC):
    """
    Base class for all services
    Provides common functionality and enforces service contracts
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def log_error(self, message: str, error: Exception, context: Optional[Dict[str, Any]] = None):
        """
        Log error with context
        
        Args:
            message: Error message
            error: Exception object
            context: Additional context dictionary
        """
        context_str = f" Context: {context}" if context else ""
        self.logger.error(f"{message}{context_str}", exc_info=True)
    
    def log_warning(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log warning with context"""
        context_str = f" Context: {context}" if context else ""
        self.logger.warning(f"{message}{context_str}")
    
    def log_info(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log info with context"""
        context_str = f" Context: {context}" if context else ""
        self.logger.info(f"{message}{context_str}")
    
    def log_debug(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log debug with context"""
        context_str = f" Context: {context}" if context else ""
        self.logger.debug(f"{message}{context_str}")

