"""
Data refresh strategies (Strategy Pattern)
Defines different refresh modes: scheduled, on-demand, periodic/live
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
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
    PRICE_INTRADAY_5M = "price_intraday_5m"  # Updated from 15m to 5m
    FUNDAMENTALS = "fundamentals"
    INDICATORS = "indicators"
    NEWS = "news"
    EARNINGS = "earnings"
    INDUSTRY_PEERS = "industry_peers"
    CORPORATE_ACTIONS = "corporate_actions"
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
    INSTITUTIONAL_BUYING = "institutional_buying"  # Added institutional buying
    # Data aggregation and calculations
    WEEKLY_AGGREGATION = "weekly_aggregation"
    GROWTH_CALCULATIONS = "growth_calculations"
    # Growth metrics (FMP growth APIs)
    INCOME_STATEMENT_GROWTH = "income_statement_growth"
    BALANCE_SHEET_GROWTH = "balance_sheet_growth"
    CASH_FLOW_GROWTH = "cash_flow_growth"
    FINANCIAL_GROWTH = "financial_growth"
    # Grading and analyst data types (FMP primary data source)
    STOCK_GRADES = "stock_grades"
    ANALYST_RATINGS = "analyst_ratings"
    CONSENSUS_DATA = "consensus_data"
    PRICE_TARGETS = "price_targets"
    RATINGS_SNAPSHOT = "ratings_snapshot"
    HISTORICAL_GRADES = "historical_grades"
    EARNINGS_TRANSCRIPTS = "earnings_transcripts"
    FINANCIAL_SCORES = "financial_scores"
    KEY_METRICS_TTM = "key_metrics_ttm"
    OWNER_EARNINGS = "owner_earnings"


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
            # High priority - core market data
            DataType.PRICE_HISTORICAL: 10,
            DataType.PRICE_CURRENT: 10,
            DataType.PRICE_INTRADAY_5M: 9,  # Updated from 15m to 5m
            
            # Very high priority - analyst/grading data (FMP primary)
            DataType.STOCK_GRADES: 10,
            DataType.ANALYST_RATINGS: 9,
            DataType.CONSENSUS_DATA: 9,
            DataType.PRICE_TARGETS: 8,
            DataType.RATINGS_SNAPSHOT: 8,
            
            # High priority - financial data
            DataType.FUNDAMENTALS: 8,
            DataType.INDICATORS: 8,
            DataType.INCOME_STATEMENTS: 7,
            DataType.BALANCE_SHEETS: 7,
            DataType.CASH_FLOW_STATEMENTS: 7,
            DataType.FINANCIAL_RATIOS: 7,
            DataType.KEY_METRICS_TTM: 7,
            DataType.FINANCIAL_SCORES: 6,
            
            # Medium priority - signals and analysis
            DataType.SIGNALS: 7,
            DataType.REPORTS: 6,
            DataType.OWNER_EARNINGS: 6,
            
            # Medium priority - news and events
            DataType.NEWS: 5,
            DataType.EARNINGS: 5,
            DataType.EARNINGS_TRANSCRIPTS: 5,
            DataType.HISTORICAL_GRADES: 5,
            
            # Lower priority - reference data
            DataType.INDUSTRY_PEERS: 3,
            DataType.CORPORATE_ACTIONS: 3,
            DataType.INSTITUTIONAL_BUYING: 4,  # Added institutional buying
            DataType.SHORT_INTEREST: 2,
            DataType.SHORT_VOLUME: 2,
            DataType.SHARE_FLOAT: 2,
            DataType.RISK_FACTORS: 2,
            
            # Growth metrics - medium priority for analysis
            DataType.INCOME_STATEMENT_GROWTH: 6,
            DataType.BALANCE_SHEET_GROWTH: 6,
            DataType.CASH_FLOW_GROWTH: 6,
            DataType.FINANCIAL_GROWTH: 7,  # Comprehensive growth data
            
            # Lowest priority - aggregations
            DataType.WEEKLY_AGGREGATION: 1,
            DataType.GROWTH_CALCULATIONS: 1,
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
            # Real-time data
            DataType.PRICE_CURRENT: timedelta(minutes=5),
            DataType.PRICE_INTRADAY_5M: timedelta(minutes=5),  # Updated from 15m to 5m
            
            # High-frequency analyst data
            DataType.STOCK_GRADES: timedelta(hours=1),
            DataType.ANALYST_RATINGS: timedelta(hours=2),
            DataType.CONSENSUS_DATA: timedelta(hours=2),
            DataType.PRICE_TARGETS: timedelta(hours=3),
            DataType.RATINGS_SNAPSHOT: timedelta(hours=4),
            
            # Regular market data
            DataType.NEWS: timedelta(hours=1),
            DataType.EARNINGS: timedelta(hours=6),
            DataType.FUNDAMENTALS: timedelta(hours=12),
            DataType.INDICATORS: timedelta(hours=12),
            
            # Financial statements (less frequent)
            DataType.INCOME_STATEMENTS: timedelta(hours=24),
            DataType.BALANCE_SHEETS: timedelta(hours=24),
            DataType.CASH_FLOW_STATEMENTS: timedelta(hours=24),
            DataType.FINANCIAL_RATIOS: timedelta(hours=18),
            DataType.KEY_METRICS_TTM: timedelta(hours=18),
            DataType.FINANCIAL_SCORES: timedelta(hours=24),
            
            # Event-driven data
            DataType.EARNINGS_TRANSCRIPTS: timedelta(hours=12),
            DataType.INSTITUTIONAL_BUYING: timedelta(hours=6),  # Added institutional buying
            DataType.HISTORICAL_GRADES: timedelta(hours=24),
            DataType.OWNER_EARNINGS: timedelta(hours=24),
            
            # Growth metrics - refresh daily (growth changes slowly)
            DataType.INCOME_STATEMENT_GROWTH: timedelta(hours=24),
            DataType.BALANCE_SHEET_GROWTH: timedelta(hours=24),
            DataType.CASH_FLOW_GROWTH: timedelta(hours=24),
            DataType.FINANCIAL_GROWTH: timedelta(hours=24),
            
            # Reference data (low frequency)
            DataType.INDUSTRY_PEERS: timedelta(days=1),
            DataType.CORPORATE_ACTIONS: timedelta(hours=12),
            DataType.SHORT_INTEREST: timedelta(days=1),
            DataType.SHORT_VOLUME: timedelta(days=1),
            DataType.SHARE_FLOAT: timedelta(days=7),
            DataType.RISK_FACTORS: timedelta(days=3),
            
            # Aggregations (lowest frequency)
            DataType.WEEKLY_AGGREGATION: timedelta(days=1),
            DataType.GROWTH_CALCULATIONS: timedelta(days=1),
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

        # Normalize to timezone-aware UTC to avoid "offset-naive and offset-aware" errors
        # when DB timestamps come back with tzinfo.
        if getattr(last_refresh, "tzinfo", None) is None:
            last_refresh_utc = last_refresh.replace(tzinfo=timezone.utc)
        else:
            last_refresh_utc = last_refresh.astimezone(timezone.utc)
        
        interval = self.get_refresh_interval(data_type)
        return datetime.now(timezone.utc) - last_refresh_utc >= interval
    
    def get_refresh_interval(self, data_type: DataType) -> timedelta:
        """Get interval for data type"""
        return self.intervals.get(data_type, timedelta(hours=1))
    
    def get_priority(self, data_type: DataType) -> int:
        """Priority for periodic refresh"""
        priorities = {
            # Highest priority - real-time data
            DataType.PRICE_CURRENT: 20,
            DataType.PRICE_INTRADAY_5M: 19,
            
            # Very high priority - analyst data (FMP primary)
            DataType.STOCK_GRADES: 18,
            DataType.ANALYST_RATINGS: 17,
            DataType.CONSENSUS_DATA: 17,
            DataType.PRICE_TARGETS: 16,
            DataType.RATINGS_SNAPSHOT: 15,
            
            # High priority - market data
            DataType.NEWS: 15,
            DataType.EARNINGS: 12,
            DataType.FUNDAMENTALS: 10,
            DataType.INDICATORS: 10,
            
            # Medium priority - financial data
            DataType.INCOME_STATEMENTS: 9,
            DataType.BALANCE_SHEETS: 9,
            DataType.CASH_FLOW_STATEMENTS: 9,
            DataType.FINANCIAL_RATIOS: 8,
            DataType.KEY_METRICS_TTM: 8,
            DataType.FINANCIAL_SCORES: 7,
            
            # Lower priority - events and reference
            DataType.EARNINGS_TRANSCRIPTS: 6,
            DataType.HISTORICAL_GRADES: 6,
            DataType.OWNER_EARNINGS: 6,
            DataType.INDUSTRY_PEERS: 4,
            DataType.CORPORATE_ACTIONS: 4,
            DataType.SHORT_INTEREST: 3,
            DataType.SHORT_VOLUME: 3,
            DataType.SHARE_FLOAT: 2,
            DataType.RISK_FACTORS: 2,
            
            # Lowest priority - aggregations
            DataType.WEEKLY_AGGREGATION: 1,
            DataType.GROWTH_CALCULATIONS: 1,
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

        if getattr(last_refresh, "tzinfo", None) is None:
            last_refresh_utc = last_refresh.replace(tzinfo=timezone.utc)
        else:
            last_refresh_utc = last_refresh.astimezone(timezone.utc)

        return datetime.now(timezone.utc) - last_refresh_utc > self.max_age
    
    def get_refresh_interval(self, data_type: DataType) -> timedelta:
        """Live refresh uses max_age interval"""
        return self.max_age
    
    def get_priority(self, data_type: DataType) -> int:
        """Highest priority for live data"""
        return 200

