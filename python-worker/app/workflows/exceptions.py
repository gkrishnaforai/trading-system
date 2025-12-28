"""
Workflow-specific exceptions
"""
from app.exceptions import TradingSystemError


class WorkflowException(TradingSystemError):
    """Base exception for workflow errors"""
    pass


class WorkflowGateFailed(WorkflowException):
    """Raised when a workflow gate fails"""
    
    def __init__(self, message: str, action: str = None, gate_name: str = None, details: dict = None):
        details = details or {}
        if action:
            details['action'] = action
        if gate_name:
            details['gate_name'] = gate_name
        super().__init__(message, details=details)
        self.action = action
        self.gate_name = gate_name


class WorkflowStageFailed(WorkflowException):
    """Raised when a workflow stage fails"""
    
    def __init__(self, message: str, stage: str = None, symbol: str = None, details: dict = None):
        details = details or {}
        if stage:
            details['stage'] = stage
        if symbol:
            details['symbol'] = symbol
        super().__init__(message, details=details)
        self.stage = stage
        self.symbol = symbol


class DuplicateDataError(WorkflowException):
    """Raised when duplicate data is detected"""
    
    def __init__(self, message: str, symbol: str = None, date: str = None, details: dict = None):
        details = details or {}
        if symbol:
            details['symbol'] = symbol
        if date:
            details['date'] = date
        super().__init__(message, details=details)
        self.symbol = symbol
        self.date = date

