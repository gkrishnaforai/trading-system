"""
Custom exception hierarchy
Fail fast with clear, actionable error messages
"""
from typing import Optional


class TradingSystemError(Exception):
    """Base exception for all trading system errors"""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class DataSourceError(TradingSystemError):
    """Error from data source (Yahoo Finance, etc.)"""
    pass


class IndicatorCalculationError(TradingSystemError):
    """Error during indicator calculation"""
    pass


class StrategyExecutionError(TradingSystemError):
    """Error during strategy execution"""
    pass


class DatabaseError(TradingSystemError):
    """Database operation error"""
    pass


class ValidationError(TradingSystemError):
    """Data validation error"""
    pass


class ConfigurationError(TradingSystemError):
    """Configuration error"""
    pass


class ServiceUnavailableError(TradingSystemError):
    """Service unavailable error (circuit breaker, etc.)"""
    pass


class AlertNotificationError(TradingSystemError):
    """Error during alert notification (email, SMS, etc.)"""
    pass

