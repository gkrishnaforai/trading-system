"""
Update Strategy - Separates Daily vs Periodic Updates
Industry Standard: Different update frequencies for different data types

SOLID: Single Responsibility - determines what needs updating and when
DRY: Centralized logic for update frequency decisions
"""
import logging
from typing import List, Dict, Any, Set, Optional
from datetime import datetime, date, timedelta
from enum import Enum

from app.database import db

logger = logging.getLogger(__name__)


class DataUpdateType(Enum):
    """Types of data updates"""
    DAILY_EOD = "daily_eod"  # End-of-day: Price, Volume, Indicators, Signals
    QUARTERLY = "quarterly"  # Fundamentals, Earnings
    EVENT_BASED = "event_based"  # News, Analyst ratings, Macro events
    ON_DEMAND = "on_demand"  # Manual triggers


class UpdateStrategy:
    """
    Determines what data needs updating based on frequency and last update time
    
    Industry Standard:
    - Daily: Price, Volume, Indicators (recomputed), Signals
    - Quarterly: Fundamentals, Earnings
    - Event-based: News, Analyst ratings
    """
    
    # Data type to update frequency mapping
    DATA_TYPE_FREQUENCY = {
        # Daily EOD updates
        'price_historical': DataUpdateType.DAILY_EOD,
        'volume': DataUpdateType.DAILY_EOD,
        'indicators': DataUpdateType.DAILY_EOD,  # Recomputed daily
        'signals': DataUpdateType.DAILY_EOD,  # Generated daily
        
        # Quarterly updates
        'fundamentals': DataUpdateType.QUARTERLY,
        'earnings': DataUpdateType.QUARTERLY,
        'industry_peers': DataUpdateType.QUARTERLY,
        
        # Event-based updates
        'news': DataUpdateType.EVENT_BASED,
        'analyst_ratings': DataUpdateType.EVENT_BASED,
    }
    
    def __init__(self):
        self.quarterly_update_months = [3, 6, 9, 12]  # End of quarters
    
    def get_symbols_needing_daily_update(self) -> List[str]:
        """
        Get symbols that need daily EOD update
        
        Industry Standard: All symbols in:
        - Active portfolios
        - Active watchlists
        - Recent signals/indicators
        """
        symbols = set()
        
        # From holdings
        holdings = db.execute_query(
            "SELECT DISTINCT stock_symbol FROM holdings WHERE stock_symbol IS NOT NULL AND stock_symbol != ''"
        )
        symbols.update(h['stock_symbol'] for h in holdings)
        
        # From watchlists
        watchlist_items = db.execute_query(
            "SELECT DISTINCT stock_symbol FROM watchlist_items WHERE stock_symbol IS NOT NULL AND stock_symbol != ''"
        )
        symbols.update(w['stock_symbol'] for w in watchlist_items)
        
        # From recent indicators (last 30 days)
        recent_indicators = db.execute_query(
            """
            SELECT DISTINCT stock_symbol FROM aggregated_indicators
            WHERE date >= DATE('now', '-30 days')
            AND stock_symbol IS NOT NULL AND stock_symbol != ''
            """
        )
        symbols.update(i['stock_symbol'] for i in recent_indicators)
        
        return sorted(list(symbols))
    
    def get_symbols_needing_quarterly_update(self) -> List[str]:
        """
        Get symbols that need quarterly update
        
        Industry Standard: Update fundamentals/earnings:
        - At end of quarter (March, June, September, December)
        - Or if last update > 90 days old
        """
        current_month = datetime.now().month
        current_date = date.today()
        quarter_start = date(current_date.year, ((current_month - 1) // 3) * 3 + 1, 1)
        days_since_quarter_start = (current_date - quarter_start).days
        
        # Update if:
        # 1. End of quarter (last month of quarter)
        # 2. Or last update > 90 days old
        should_update = (
            current_month in self.quarterly_update_months or
            days_since_quarter_start > 90
        )
        
        if not should_update:
            return []
        
        # Get symbols with stale fundamentals (> 90 days)
        stale_fundamentals = db.execute_query(
            """
            SELECT DISTINCT stock_symbol FROM raw_market_data
            WHERE fundamental_data IS NOT NULL
            AND date < DATE('now', '-90 days')
            AND stock_symbol IS NOT NULL AND stock_symbol != ''
            """
        )
        
        return [s['stock_symbol'] for s in stale_fundamentals]
    
    def get_symbols_needing_event_update(self, event_type: str) -> List[str]:
        """
        Get symbols that need event-based update
        
        Args:
            event_type: 'news', 'analyst_ratings', etc.
        """
        # Event-based updates are triggered by:
        # - Earnings calendar
        # - Analyst rating changes
        # - News events
        # - Macro events
        
        # For now, return symbols from active portfolios/watchlists
        # In production, would check:
        # - Earnings calendar for upcoming earnings
        # - Analyst rating API for recent changes
        # - News feed for relevant events
        
        return self.get_symbols_needing_daily_update()
    
    def should_update_data_type(
        self,
        symbol: str,
        data_type: str,
        last_update_date: Optional[date] = None
    ) -> bool:
        """
        Determine if data type should be updated
        
        Industry Standard Logic:
        - Daily: Update if last update < today
        - Quarterly: Update if last update > 90 days or end of quarter
        - Event-based: Update based on events
        """
        update_type = self.DATA_TYPE_FREQUENCY.get(data_type)
        
        if not update_type:
            logger.warning(f"Unknown data type: {data_type}")
            return False
        
        if update_type == DataUpdateType.DAILY_EOD:
            # Daily: Update if not updated today
            if not last_update_date:
                return True
            return last_update_date < date.today()
        
        elif update_type == DataUpdateType.QUARTERLY:
            # Quarterly: Update if > 90 days or end of quarter
            if not last_update_date:
                return True
            
            days_old = (date.today() - last_update_date).days
            current_month = datetime.now().month
            
            return days_old > 90 or current_month in self.quarterly_update_months
        
        elif update_type == DataUpdateType.EVENT_BASED:
            # Event-based: Update based on events (always return True for now)
            # In production, would check event calendar
            return True
        
        return False
    
    def get_last_update_date(self, symbol: str, data_type: str) -> Optional[date]:
        """Get last update date for symbol and data type"""
        try:
            if data_type == 'price_historical':
                result = db.execute_query(
                    """
                    SELECT MAX(date) as last_date FROM raw_market_data
                    WHERE stock_symbol = :symbol
                    """,
                    {"symbol": symbol}
                )
            elif data_type == 'indicators':
                result = db.execute_query(
                    """
                    SELECT MAX(date) as last_date FROM aggregated_indicators
                    WHERE stock_symbol = :symbol
                    """,
                    {"symbol": symbol}
                )
            elif data_type == 'fundamentals':
                result = db.execute_query(
                    """
                    SELECT MAX(date) as last_date FROM raw_market_data
                    WHERE stock_symbol = :symbol AND fundamental_data IS NOT NULL
                    """,
                    {"symbol": symbol}
                )
            else:
                return None
            
            if result and result[0]['last_date']:
                last_date = result[0]['last_date']
                if isinstance(last_date, str):
                    return datetime.strptime(last_date, '%Y-%m-%d').date()
                elif isinstance(last_date, datetime):
                    return last_date.date()
                return last_date
            
            return None
        except Exception as e:
            logger.error(f"Error getting last update date for {symbol} {data_type}: {e}")
            return None

