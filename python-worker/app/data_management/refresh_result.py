"""
Refresh result models for tracking success/failure of data refreshes
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class RefreshStatus(Enum):
    """Status of a data refresh operation"""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # Data was fresh, no refresh needed
    PENDING = "pending"


@dataclass
class DataTypeRefreshResult:
    """Result of refreshing a single data type"""
    data_type: str
    status: RefreshStatus
    message: str
    error: Optional[str] = None
    rows_affected: int = 0
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "data_type": self.data_type,
            "status": self.status.value,
            "message": self.message,
            "error": self.error,
            "rows_affected": self.rows_affected,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class SymbolRefreshResult:
    """Result of refreshing all data types for a symbol"""
    symbol: str
    results: Dict[str, DataTypeRefreshResult]
    total_requested: int
    total_successful: int
    total_failed: int
    total_skipped: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "symbol": self.symbol,
            "summary": {
                "total_requested": self.total_requested,
                "total_successful": self.total_successful,
                "total_failed": self.total_failed,
                "total_skipped": self.total_skipped,
            },
            "results": {
                dt: result.to_dict() 
                for dt, result in self.results.items()
            }
        }

