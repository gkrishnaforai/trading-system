"""
Market Movers Service
Identifies top gainers, losers, and most active stocks
Industry Standard: Market movers calculation
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta
from enum import Enum

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors
from app.utils.validation_patterns import validate_numeric_range


class MoverType(Enum):
    """Type of market mover"""
    GAINERS = "gainers"
    LOSERS = "losers"
    MOST_ACTIVE = "most_active"


class Period(Enum):
    """Time period for movers"""
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YTD = "ytd"


class MarketMoversService(BaseService):
    """
    Service for calculating and retrieving market movers
    
    SOLID: Single Responsibility - only handles market movers
    """
    
    def __init__(self):
        """Initialize market movers service"""
        super().__init__()
    
    @handle_database_errors
    def calculate_market_movers(self, period: str = "day", limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
        """
        Calculate market movers for a given period
        
        Args:
            period: Time period (day, week, month, ytd)
            limit: Maximum number of results per category
        
        Returns:
            Dictionary with gainers, losers, and most_active lists
        """
        try:
            # Get date range for period
            end_date = date.today()
            start_date = self._get_start_date_for_period(period, end_date)
            
            # Get all symbols with price data in the period
            query = """
                SELECT DISTINCT stock_symbol
                FROM live_prices
                WHERE timestamp >= :start_date
                ORDER BY stock_symbol
            """
            symbols_result = db.execute_query(query, {
                "start_date": start_date.isoformat()
            })
            symbols = [s['stock_symbol'] for s in symbols_result]
            
            if not symbols:
                return {
                    "gainers": [],
                    "losers": [],
                    "most_active": [],
                    "period": period,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Calculate movers for each symbol
            movers = []
            for symbol in symbols:
                mover_data = self._calculate_symbol_mover(symbol, start_date, end_date, period)
                if mover_data:
                    movers.append(mover_data)
            
            # Sort and get top movers
            gainers = sorted(
                [m for m in movers if m['price_change_percent'] > 0],
                key=lambda x: x['price_change_percent'],
                reverse=True
            )[:limit]
            
            losers = sorted(
                [m for m in movers if m['price_change_percent'] < 0],
                key=lambda x: x['price_change_percent']
            )[:limit]
            
            most_active = sorted(
                movers,
                key=lambda x: x.get('volume', 0),
                reverse=True
            )[:limit]
            
            # Save to database
            self._save_market_movers(movers, period)
            
            return {
                "gainers": gainers,
                "losers": losers,
                "most_active": most_active,
                "period": period,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.log_error("Error calculating market movers", e, context={'period': period, 'limit': limit})
            raise DatabaseError(f"Failed to calculate market movers: {str(e)}") from e
    
    def get_market_movers(self, mover_type: str, period: str = "day", limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get market movers from database
        
        Args:
            mover_type: Type of mover (gainers, losers, most_active)
            period: Time period (day, week, month, ytd)
            limit: Maximum number of results
        
        Returns:
            List of market movers
        """
        try:
            # Get latest movers from database
            query = """
                SELECT stock_symbol, price_change, price_change_percent, volume, 
                       market_cap, sector, industry, timestamp
                FROM market_movers
                WHERE period = :period
                ORDER BY timestamp DESC
                LIMIT :limit
            """
            
            if mover_type == "gainers":
                query = """
                    SELECT stock_symbol, price_change, price_change_percent, volume,
                           market_cap, sector, industry, timestamp
                    FROM market_movers
                    WHERE period = :period AND price_change_percent > 0
                    ORDER BY price_change_percent DESC, timestamp DESC
                    LIMIT :limit
                """
            elif mover_type == "losers":
                query = """
                    SELECT stock_symbol, price_change, price_change_percent, volume,
                           market_cap, sector, industry, timestamp
                    FROM market_movers
                    WHERE period = :period AND price_change_percent < 0
                    ORDER BY price_change_percent ASC, timestamp DESC
                    LIMIT :limit
                """
            elif mover_type == "most_active":
                query = """
                    SELECT stock_symbol, price_change, price_change_percent, volume,
                           market_cap, sector, industry, timestamp
                    FROM market_movers
                    WHERE period = :period
                    ORDER BY volume DESC, timestamp DESC
                    LIMIT :limit
                """
            
            result = db.execute_query(query, {
                "period": period,
                "limit": limit
            })
            
            return [
                {
                    "symbol": r['stock_symbol'],
                    "price_change": r['price_change'],
                    "price_change_percent": r['price_change_percent'],
                    "volume": r.get('volume'),
                    "market_cap": r.get('market_cap'),
                    "sector": r.get('sector'),
                    "industry": r.get('industry'),
                    "timestamp": r['timestamp']
                }
                for r in result
            ]
            
        except Exception as e:
            self.log_error("Error getting market movers", e, context={'period': period})
            raise DatabaseError(f"Failed to get market movers: {str(e)}", details={'period': period}) from e
    
    def _calculate_symbol_mover(self, symbol: str, start_date: date, end_date: date, period: str) -> Optional[Dict[str, Any]]:
        """Calculate mover data for a single symbol"""
        try:
            # Get first and last price in period
            query = """
                SELECT price, volume, timestamp
                FROM live_prices
                WHERE stock_symbol = :symbol
                  AND date(timestamp) >= :start_date
                  AND date(timestamp) <= :end_date
                ORDER BY timestamp ASC
                LIMIT 1
            """
            first_result = db.execute_query(query, {
                "symbol": symbol,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            })
            
            query = """
                SELECT price, volume, timestamp
                FROM live_prices
                WHERE stock_symbol = :symbol
                  AND date(timestamp) >= :start_date
                  AND date(timestamp) <= :end_date
                ORDER BY timestamp DESC
                LIMIT 1
            """
            last_result = db.execute_query(query, {
                "symbol": symbol,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            })
            
            if not first_result or not last_result:
                return None
            
            first_price = first_result[0]['price']
            last_price = last_result[0]['price']
            
            # Get total volume
            volume_query = """
                SELECT COALESCE(SUM(volume), 0) as total_volume
                FROM live_prices
                WHERE stock_symbol = :symbol
                  AND date(timestamp) >= :start_date
                  AND date(timestamp) <= :end_date
            """
            volume_result = db.execute_query(volume_query, {
                "symbol": symbol,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            })
            total_volume = volume_result[0]['total_volume'] if volume_result else 0
            
            price_change = last_price - first_price
            price_change_percent = (price_change / first_price * 100) if first_price > 0 else 0
            
            # Get sector/industry from holdings or watchlists
            sector_query = """
                SELECT sector FROM holdings WHERE stock_symbol = :symbol LIMIT 1
                UNION
                SELECT sector FROM watchlist_items WHERE stock_symbol = :symbol LIMIT 1
            """
            sector_result = db.execute_query(sector_query, {"symbol": symbol})
            sector = sector_result[0]['sector'] if sector_result else None
            
            return {
                "symbol": symbol,
                "price_change": price_change,
                "price_change_percent": price_change_percent,
                "volume": total_volume,
                "sector": sector,
                "period": period
            }
            
        except Exception as e:
            self.log_warning(f"Error calculating mover for {symbol}", context={'symbol': symbol, 'error': str(e)})
            return None
    
    def _save_market_movers(self, movers: List[Dict[str, Any]], period: str):
        """Save market movers to database"""
        try:
            for mover in movers:
                query = """
                    INSERT OR REPLACE INTO market_movers
                    (stock_symbol, period, price_change, price_change_percent, volume, sector, timestamp)
                    VALUES (:symbol, :period, :price_change, :price_change_percent, :volume, :sector, CURRENT_TIMESTAMP)
                """
                db.execute_update(query, {
                    "symbol": mover['symbol'],
                    "period": period,
                    "price_change": mover['price_change'],
                    "price_change_percent": mover['price_change_percent'],
                    "volume": mover.get('volume', 0),
                    "sector": mover.get('sector')
                })
        except Exception as e:
            self.log_error("Error saving market movers", e, context={'period': period})
            # Don't raise - this is non-critical
    
    def _get_start_date_for_period(self, period: str, end_date: date) -> date:
        """Get start date for a given period"""
        if period == "day":
            return end_date
        elif period == "week":
            return end_date - timedelta(days=7)
        elif period == "month":
            return end_date - timedelta(days=30)
        elif period == "ytd":
            return date(end_date.year, 1, 1)
        else:
            return end_date

