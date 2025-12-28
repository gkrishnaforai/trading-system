"""
Sector Performance Service
Calculates sector and industry performance metrics
Industry Standard: Sector analysis and heat maps
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, date
import json

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors


class SectorPerformanceService(BaseService):
    """
    Service for calculating sector and industry performance
    
    SOLID: Single Responsibility - only handles sector performance
    """
    
    def __init__(self):
        """Initialize sector performance service"""
        super().__init__()
    
    @handle_database_errors
    def calculate_sector_performance(self, snapshot_date: date = None) -> Dict[str, Any]:
        """
        Calculate performance for all sectors
        
        Args:
            snapshot_date: Date for snapshot (default: today)
        
        Returns:
            Dictionary with sector performance data
        """
        if snapshot_date is None:
            snapshot_date = date.today()
        
        try:
            # Get all sectors from holdings and watchlists
            query = """
                SELECT DISTINCT sector
                FROM holdings
                WHERE sector IS NOT NULL AND sector != ''
                UNION
                SELECT DISTINCT sector
                FROM watchlist_items
                WHERE sector IS NOT NULL AND sector != ''
            """
            sectors_result = db.execute_query(query)
            sectors = [s['sector'] for s in sectors_result]
            
            if not sectors:
                return {
                    "sectors": [],
                    "timestamp": datetime.now().isoformat()
                }
            
            sector_performances = []
            for sector in sectors:
                performance = self._calculate_single_sector_performance(sector, snapshot_date)
                if performance:
                    sector_performances.append(performance)
                    # Save to database
                    self._save_sector_performance(performance, snapshot_date)
            
            # Sort by average price change
            sector_performances.sort(
                key=lambda x: x.get('avg_price_change_percent', 0),
                reverse=True
            )
            
            return {
                "sectors": sector_performances,
                "timestamp": datetime.now().isoformat(),
                "date": snapshot_date.isoformat()
            }
            
        except Exception as e:
            self.log_error("Error calculating sector performance", e, context={'snapshot_date': str(snapshot_date)})
            raise DatabaseError(f"Failed to calculate sector performance: {str(e)}") from e
    
    def get_sector_performance(self, sector: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get sector performance from database
        
        Args:
            sector: Specific sector (None for all)
            limit: Maximum number of results
        
        Returns:
            List of sector performance data
        """
        try:
            if sector:
                query = """
                    SELECT sector, date, total_stocks, avg_price_change, avg_price_change_percent,
                           gainers_count, losers_count, neutral_count, top_stocks, market_cap_total
                    FROM sector_performance
                    WHERE sector = :sector
                    ORDER BY date DESC
                    LIMIT :limit
                """
                result = db.execute_query(query, {"sector": sector, "limit": limit})
            else:
                query = """
                    SELECT sector, date, total_stocks, avg_price_change, avg_price_change_percent,
                           gainers_count, losers_count, neutral_count, top_stocks, market_cap_total
                    FROM sector_performance
                    WHERE date = (SELECT MAX(date) FROM sector_performance)
                    ORDER BY avg_price_change_percent DESC
                    LIMIT :limit
                """
                result = db.execute_query(query, {"limit": limit})
            
            return [
                {
                    "sector": r['sector'],
                    "date": r['date'],
                    "total_stocks": r['total_stocks'],
                    "avg_price_change": r['avg_price_change'],
                    "avg_price_change_percent": r['avg_price_change_percent'],
                    "gainers_count": r['gainers_count'],
                    "losers_count": r['losers_count'],
                    "neutral_count": r['neutral_count'],
                    "top_stocks": json.loads(r['top_stocks']) if r.get('top_stocks') else [],
                    "market_cap_total": r.get('market_cap_total')
                }
                for r in result
            ]
            
        except Exception as e:
            self.log_error("Error getting sector performance", e, context={'sector': sector})
            raise DatabaseError(f"Failed to get sector performance: {str(e)}") from e
    
    def _calculate_single_sector_performance(self, sector: str, snapshot_date: date) -> Optional[Dict[str, Any]]:
        """Calculate performance for a single sector"""
        try:
            # Get all stocks in this sector from holdings and watchlists
            query = """
                SELECT DISTINCT stock_symbol
                FROM holdings
                WHERE sector = :sector
                UNION
                SELECT DISTINCT stock_symbol
                FROM watchlist_items
                WHERE sector = :sector
            """
            symbols_result = db.execute_query(query, {"sector": sector})
            symbols = [s['stock_symbol'] for s in symbols_result]
            
            if not symbols:
                return None
            
            # Calculate aggregate metrics
            total_stocks = len(symbols)
            price_changes = []
            gainers = 0
            losers = 0
            neutral = 0
            top_stocks = []
            
            for symbol in symbols:
                # Get price change from live_prices or holdings
                price_change_query = """
                    SELECT price_change_percent_since_added
                    FROM watchlist_items
                    WHERE stock_symbol = :symbol
                    LIMIT 1
                """
                result = db.execute_query(price_change_query, {"symbol": symbol})
                
                if result and result[0].get('price_change_percent_since_added') is not None:
                    change_pct = result[0]['price_change_percent_since_added']
                    price_changes.append(change_pct)
                    
                    if change_pct > 5:
                        gainers += 1
                    elif change_pct < -5:
                        losers += 1
                    else:
                        neutral += 1
                    
                    top_stocks.append({
                        "symbol": symbol,
                        "change_percent": change_pct
                    })
            
            # Calculate averages
            avg_price_change = sum(price_changes) / len(price_changes) if price_changes else 0
            avg_price_change_percent = avg_price_change  # Already in percent
            
            # Sort top stocks
            top_stocks.sort(key=lambda x: x['change_percent'], reverse=True)
            top_stocks = top_stocks[:5]
            
            return {
                "sector": sector,
                "total_stocks": total_stocks,
                "avg_price_change": avg_price_change,
                "avg_price_change_percent": avg_price_change_percent,
                "gainers_count": gainers,
                "losers_count": losers,
                "neutral_count": neutral,
                "top_stocks": top_stocks
            }
            
        except Exception as e:
            self.log_warning(f"Error calculating performance for sector {sector}", context={'sector': sector, 'error': str(e)})
            return None
    
    def _save_sector_performance(self, performance: Dict[str, Any], snapshot_date: date):
        """Save sector performance to database"""
        try:
            query = """
                INSERT OR REPLACE INTO sector_performance
                (sector, date, total_stocks, avg_price_change, avg_price_change_percent,
                 gainers_count, losers_count, neutral_count, top_stocks)
                VALUES (:sector, :date, :total_stocks, :avg_price_change, :avg_price_change_percent,
                        :gainers_count, :losers_count, :neutral_count, :top_stocks)
            """
            db.execute_update(query, {
                "sector": performance['sector'],
                "date": snapshot_date.isoformat(),
                "total_stocks": performance['total_stocks'],
                "avg_price_change": performance['avg_price_change'],
                "avg_price_change_percent": performance['avg_price_change_percent'],
                "gainers_count": performance['gainers_count'],
                "losers_count": performance['losers_count'],
                "neutral_count": performance['neutral_count'],
                "top_stocks": json.dumps(performance['top_stocks'])
            })
        except Exception as e:
            self.log_error("Error saving sector performance", e, context={'sector': performance.get('sector')})
            # Don't raise - this is non-critical

