"""
Data refresh strategies (Strategy Pattern)
Defines different refresh modes: scheduled, on-demand, periodic/live
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class RefreshMode(Enum):
    """Data refresh modes"""
    SCHEDULED = "scheduled"  # Cron-based (e.g., 1 AM daily)
    ON_DEMAND = "on_demand"  # User-triggered
    PERIODIC = "periodic"  # Regular intervals (e.g., every 15 min)
    LIVE = "live"  # Real-time updates


class DataType(Enum):
    """Types of data that can be refreshed"""
    PRICE_HISTORICAL = "price_historical"
    PRICE_CURRENT = "price_current"
    PRICE_INTRADAY_15M = "price_intraday_15m"
    FUNDAMENTALS = "fundamentals"
    INDICATORS = "indicators"
    NEWS = "news"
    EARNINGS = "earnings"
    INDUSTRY_PEERS = "industry_peers"
    SIGNALS = "signals"
    REPORTS = "reports"
    # New financial data types
    INCOME_STATEMENTS = "income_statements"
    BALANCE_SHEETS = "balance_sheets"
    CASH_FLOW_STATEMENTS = "cash_flow_statements"
    FINANCIAL_RATIOS = "financial_ratios"
    SHORT_INTEREST = "short_interest"
    SHORT_VOLUME = "short_volume"
    SHARE_FLOAT = "share_float"
    RISK_FACTORS = "risk_factors"
    # Data aggregation and calculations
    WEEKLY_AGGREGATION = "weekly_aggregation"
    GROWTH_CALCULATIONS = "growth_calculations"


class BaseRefreshStrategy(ABC):
    """Base class for refresh strategies"""
    
    def __init__(self, mode: RefreshMode):
        self.mode = mode
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @abstractmethod
    def should_refresh(
        self,
        symbol: str,
        data_type: DataType,
        last_refresh: Optional[datetime] = None
    ) -> bool:
        """Determine if data should be refreshed"""
        pass
    
    @abstractmethod
    def get_refresh_interval(self, data_type: DataType) -> timedelta:
        """Get the refresh interval for a data type"""
        pass
    
    @abstractmethod
    def get_priority(self, data_type: DataType) -> int:
        """Get refresh priority (higher = more important)"""
        pass


class ScheduledRefreshStrategy(BaseRefreshStrategy):
    """Scheduled refresh (e.g., nightly at 1 AM)"""
    
    def __init__(self, schedule_time: str = "01:00"):
        super().__init__(RefreshMode.SCHEDULED)
        self.schedule_time = schedule_time
    
    def should_refresh(
        self,
        symbol: str,
        data_type: DataType,
        last_refresh: Optional[datetime] = None
    ) -> bool:
        """Refresh if scheduled time has passed since last refresh"""
        if last_refresh is None:
            return True
        
        # Check if we're past the scheduled time today
        now = datetime.now()
        schedule_hour, schedule_minute = map(int, self.schedule_time.split(":"))
        schedule_today = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
        
        # If scheduled time hasn't passed today, check yesterday
        if now < schedule_today:
            schedule_today = schedule_today - timedelta(days=1)
        
        return last_refresh < schedule_today
    
    def get_refresh_interval(self, data_type: DataType) -> timedelta:
        """Scheduled refresh happens daily"""
        return timedelta(days=1)
    
    def get_priority(self, data_type: DataType) -> int:
        """Priority for scheduled refresh"""
        priorities = {
            DataType.PRICE_HISTORICAL: 10,
            DataType.FUNDAMENTALS: 8,
            DataType.INDICATORS: 9,
            DataType.SIGNALS: 7,
            DataType.REPORTS: 6,
            DataType.NEWS: 5,
            DataType.EARNINGS: 4,
            DataType.INDUSTRY_PEERS: 3,
        }
        return priorities.get(data_type, 1)


class OnDemandRefreshStrategy(BaseRefreshStrategy):
    """On-demand refresh (user-triggered)"""
    
    def __init__(self):
        super().__init__(RefreshMode.ON_DEMAND)
    
    def should_refresh(
        self,
        symbol: str,
        data_type: DataType,
        last_refresh: Optional[datetime] = None
    ) -> bool:
        """Always refresh on demand"""
        return True
    
    def get_refresh_interval(self, data_type: DataType) -> timedelta:
        """On-demand has no interval"""
        return timedelta(0)
    
    def get_priority(self, data_type: DataType) -> int:
        """High priority for user-requested data"""
        return 100


class PeriodicRefreshStrategy(BaseRefreshStrategy):
    """Periodic refresh (regular intervals)"""
    
    def __init__(self, intervals: Dict[DataType, timedelta] = None):
        super().__init__(RefreshMode.PERIODIC)
        self.intervals = intervals or {
            DataType.PRICE_CURRENT: timedelta(minutes=15),
            DataType.PRICE_INTRADAY_15M: timedelta(minutes=15),
            DataType.NEWS: timedelta(hours=1),
            DataType.EARNINGS: timedelta(hours=6),
            DataType.FUNDAMENTALS: timedelta(hours=12),
        }
    
    def should_refresh(
        self,
        symbol: str,
        data_type: DataType,
        last_refresh: Optional[datetime] = None
    ) -> bool:
        """Refresh if interval has passed"""
        if last_refresh is None:
            return True
        
        interval = self.get_refresh_interval(data_type)
        return datetime.now() - last_refresh >= interval
    
    def get_refresh_interval(self, data_type: DataType) -> timedelta:
        """Get interval for data type"""
        return self.intervals.get(data_type, timedelta(hours=1))
    
    def get_priority(self, data_type: DataType) -> int:
        """Priority for periodic refresh"""
        priorities = {
            DataType.PRICE_CURRENT: 20,
            DataType.PRICE_INTRADAY_15M: 19,
            DataType.NEWS: 15,
            DataType.EARNINGS: 12,
            DataType.FUNDAMENTALS: 10,
        }
        return priorities.get(data_type, 5)


class LiveRefreshStrategy(BaseRefreshStrategy):
    """Live/real-time refresh"""
    
    def __init__(self, max_age: timedelta = timedelta(minutes=1)):
        super().__init__(RefreshMode.LIVE)
        self.max_age = max_age
    
    def should_refresh(
        self,
        symbol: str,
        data_type: DataType,
        last_refresh: Optional[datetime] = None
    ) -> bool:
        """Refresh if data is older than max_age"""
        if last_refresh is None:
            return True
        
        return datetime.now() - last_refresh > self.max_age
    
    def get_refresh_interval(self, data_type: DataType) -> timedelta:
        """Live refresh uses max_age interval"""
        return self.max_age
    
    def get_priority(self, data_type: DataType) -> int:
        """Highest priority for live data"""
        return 200

