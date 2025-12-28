"""
Service for managing earnings calendar data and business logic.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
import pandas as pd
from app.data_sources.yahoo_finance_source import YahooFinanceSource
from app.repositories.earnings_calendar_repository import EarningsCalendarRepository
from app.observability.logging import get_logger
from app.database import init_database

logger = get_logger("earnings_calendar_service")

class EarningsCalendarService:
    """Service for earnings calendar operations."""
    
    def __init__(self, data_source=None, repository=None):
        # Initialize database first
        init_database()
        
        self.data_source = data_source or YahooFinanceSource()
        self.repository = repository or EarningsCalendarRepository()
        self.repository.create_table()
    
    def refresh_earnings_calendar(self, symbols: List[str] = None, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """Refresh earnings calendar data for given symbols and date range."""
        try:
            logger.info(f"Refreshing earnings calendar for {len(symbols) if symbols else 'default'} symbols")
            
            # Fetch earnings calendar from data source
            earnings_data = self.data_source.fetch_earnings_calendar(symbols, start_date, end_date)
            
            if not earnings_data:
                logger.warning("No earnings data returned from data source")
                return {"status": "no_data", "count": 0}
            
            # Store in database
            inserted_count = self.repository.upsert_earnings(earnings_data)
            
            logger.info(f"Successfully refreshed {inserted_count} earnings entries")
            
            return {
                "status": "success",
                "count": inserted_count,
                "date_range": f"{start_date or 'today'} to {end_date or '90 days'}"
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh earnings calendar: {e}")
            return {"status": "error", "error": str(e)}
    
    def get_earnings_calendar(self, start_date: date = None, end_date: date = None) -> List[Dict[str, Any]]:
        """Get earnings calendar for a date range."""
        if not start_date:
            start_date = date.today()
        if not end_date:
            end_date = start_date + timedelta(days=30)
        
        return self.repository.fetch_earnings_by_date_range(start_date, end_date)
    
    def get_upcoming_earnings(self, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Get upcoming earnings within the next N days."""
        return self.repository.fetch_upcoming_earnings(days_ahead)
    
    def get_symbol_earnings(self, symbol: str, lookback_days: int = 365) -> List[Dict[str, Any]]:
        """Get earnings history for a specific symbol."""
        end_date = date.today() + timedelta(days=90)  # Include future estimates
        start_date = end_date - timedelta(days=lookback_days)
        
        return self.repository.fetch_earnings_by_symbol(symbol, start_date, end_date)
    
    def check_portfolio_earnings(self, portfolio_symbols: List[str], days_ahead: int = 30) -> Dict[str, Any]:
        """Check if any portfolio symbols have upcoming earnings."""
        end_date = date.today() + timedelta(days=days_ahead)
        start_date = date.today()
        
        portfolio_earnings = []
        for symbol in portfolio_symbols:
            symbol_earnings = self.repository.fetch_earnings_by_symbol(symbol, start_date, end_date)
            if symbol_earnings:
                portfolio_earnings.extend(symbol_earnings)
        
        # Sort by date
        portfolio_earnings.sort(key=lambda x: x.get('earnings_date'))
        
        return {
            "has_earnings": len(portfolio_earnings) > 0,
            "count": len(portfolio_earnings),
            "earnings": portfolio_earnings,
            "next_earnings": portfolio_earnings[0] if portfolio_earnings else None
        }
    
    def get_earnings_by_sector(self, sector: str, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """Get upcoming earnings for a specific sector."""
        end_date = date.today() + timedelta(days=days_ahead)
        start_date = date.today()
        
        return self.repository.fetch_earnings_by_sector(sector, start_date, end_date)
    
    def get_earnings_summary(self, start_date: date = None, end_date: date = None) -> Dict[str, Any]:
        """Get summary statistics for earnings in a date range."""
        if not start_date:
            start_date = date.today()
        if not end_date:
            end_date = start_date + timedelta(days=30)
        
        earnings = self.repository.fetch_earnings_by_date_range(start_date, end_date)
        
        if not earnings:
            return {
                "total_companies": 0, 
                "unique_symbols": 0,
                "by_sector": {}, 
                "by_date": {},
                "market_cap_distribution": {}
            }
        
        df = pd.DataFrame(earnings)
        
        # Count by sector
        sector_counts = df['sector'].value_counts().to_dict() if 'sector' in df.columns else {}
        
        # Count by date
        df['earnings_date'] = pd.to_datetime(df['earnings_date'])
        date_counts = df.groupby(df['earnings_date'].dt.date).size().to_dict()
        
        # Market cap distribution
        market_cap_stats = {}
        if 'market_cap' in df.columns:
            market_cap_stats = {
                "large_cap": len(df[df['market_cap'] > 10e9]),
                "mid_cap": len(df[(df['market_cap'] > 2e9) & (df['market_cap'] <= 10e9)]),
                "small_cap": len(df[df['market_cap'] <= 2e9])
            }
        
        return {
            "total_companies": len(earnings),
            "unique_symbols": df['symbol'].nunique() if 'symbol' in df.columns else 0,
            "by_sector": sector_counts,
            "by_date": {str(k): v for k, v in date_counts.items()},
            "market_cap_distribution": market_cap_stats
        }
    
    def cleanup_old_data(self, days_to_keep: int = 365) -> int:
        """Clean up earnings data older than specified days."""
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        deleted_count = self.repository.delete_old_earnings(cutoff_date)
        logger.info(f"Cleaned up {deleted_count} old earnings entries")
        return deleted_count
