"""
Market Overview Service
Provides market-wide statistics and dashboard data
Industry Standard: Market overview and status
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date
import json

from app.data_sources import get_data_source
from app.repositories.market_data_intraday_repository import MarketDataIntradayRepository
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.query_utils import fetch_recent_symbols

logger = logging.getLogger(__name__)


class MarketOverviewService(BaseService):
    """
    Service for market overview and dashboard data
    
    SOLID: Single Responsibility - only handles market overview
    """
    
    def __init__(self):
        """Initialize market overview service"""
        super().__init__()
        self.data_source = get_data_source()
    
    def get_market_overview(self, snapshot_date: date = None) -> Dict[str, Any]:
        """
        Get comprehensive market overview
        
        Args:
            snapshot_date: Date for snapshot (default: today)
        
        Returns:
            Dictionary with market overview data
        """
        if snapshot_date is None:
            snapshot_date = date.today()
        
        try:
            # Get market indices
            indices = self._get_market_indices()
            
            # Get market status
            market_status = self._get_market_status()
            
            # Get market statistics
            stats = self._calculate_market_statistics()
            
            # Get top movers summary
            from app.services.market_movers_service import MarketMoversService
            movers_service = MarketMoversService()
            movers = movers_service.calculate_market_movers(period="day", limit=5)
            
            overview = {
                "date": snapshot_date.isoformat(),
                "market_status": market_status,
                "indices": indices,
                "statistics": stats,
                "top_gainers": movers.get('gainers', [])[:5],
                "top_losers": movers.get('losers', [])[:5],
                "most_active": movers.get('most_active', [])[:5],
                "timestamp": datetime.now().isoformat()
            }
            
            # Save to database
            self._save_market_overview(overview, snapshot_date)
            
            return overview
            
        except Exception as e:
            logger.error(f"Error getting market overview: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get market overview: {str(e)}") from e
    
    def _get_market_indices(self) -> Dict[str, Any]:
        """Get major market indices (SPY, QQQ, DIA)"""
        try:
            indices = {}
            index_symbols = {
                "sp500": "SPY",
                "nasdaq": "QQQ",
                "dow": "DIA"
            }
            
            for index_name, symbol in index_symbols.items():
                try:
                    current_price = self.data_source.fetch_current_price(symbol)
                    if current_price:
                        # Get previous price sample for change calculation via repository
                        prices = MarketDataIntradayRepository.fetch_latest_by_symbol(symbol, interval="last", limit=2)

                        change = None
                        change_percent = None
                        if len(prices) >= 2 and prices[1].get("close") is not None:
                            prev_price = float(prices[1]["close"])
                            change = current_price - prev_price
                            change_percent = (change / prev_price * 100) if prev_price > 0 else 0
                        
                        indices[index_name] = {
                            "symbol": symbol,
                            "price": current_price,
                            "change": change,
                            "change_percent": change_percent
                        }
                except Exception as e:
                    logger.warning(f"Error fetching {index_name} data: {e}")
                    indices[index_name] = None
            
            return indices
            
        except Exception as e:
            logger.error(f"Error getting market indices: {e}", exc_info=True)
            return {}
    
    def _get_market_status(self) -> str:
        """Determine market status (open/closed/pre-market/after-hours)"""
        try:
            now = datetime.now()
            hour = now.hour
            weekday = now.weekday()  # 0 = Monday, 6 = Sunday
            
            # Market is closed on weekends
            if weekday >= 5:
                return "closed"
            
            # Market hours: 9:30 AM - 4:00 PM ET (simplified)
            if hour < 9:
                return "pre_market"
            elif hour >= 16:
                return "after_hours"
            elif 9 <= hour < 16:
                return "open"
            else:
                return "closed"
                
        except Exception as e:
            logger.warning(f"Error determining market status: {e}")
            return "closed"
    
    def _calculate_market_statistics(self) -> Dict[str, Any]:
        """Calculate market-wide statistics"""
        try:
            # Get all symbols with intraday last prices (from last 24 hours) via repository
            symbols = MarketDataIntradayRepository.fetch_recent_symbols(hours=24)

            if not symbols:
                return {
                    "total_stocks": 0,
                    "advancing": 0,
                    "declining": 0,
                    "unchanged": 0
                }

            # Count advancing/declining
            advancing = 0
            declining = 0
            unchanged = 0

            for symbol in symbols:
                result = MarketDataIntradayRepository.fetch_latest_by_symbol(symbol, interval="last", limit=2)

                if len(result) >= 2 and result[0].get("close") is not None and result[1].get("close") is not None:
                    last_close = float(result[0]["close"])
                    prev_close = float(result[1]["close"])
                    change = last_close - prev_close

                    if change > 0:
                        advancing += 1
                    elif change < 0:
                        declining += 1
                    else:
                        unchanged += 1

            return {
                "total_stocks": len(symbols),
                "advancing": advancing,
                "declining": declining,
                "unchanged": unchanged
            }

        except Exception as e:
            logger.error(f"Error calculating market statistics: {e}", exc_info=True)
            return {
                "total_stocks": 0,
                "advancing": 0,
                "declining": 0,
                "unchanged": 0
            }
    
    def _save_market_overview(self, overview: Dict[str, Any], snapshot_date: date):
        """Save market overview to database"""
        try:
            indices = overview.get('indices', {})
            stats = overview.get('statistics', {})
            
            # Postgres-only: use UPSERT
            query = """
                INSERT INTO market_overview
                (date, market_status, sp500_price, sp500_change, sp500_change_percent,
                 nasdaq_price, nasdaq_change, nasdaq_change_percent,
                 dow_price, dow_change, dow_change_percent,
                 total_volume, advancing_stocks, declining_stocks, unchanged_stocks)
                VALUES (:date, :market_status, :sp500_price, :sp500_change, :sp500_change_percent,
                        :nasdaq_price, :nasdaq_change, :nasdaq_change_percent,
                        :dow_price, :dow_change, :dow_change_percent,
                        :total_volume, :advancing, :declining, :unchanged)
                ON CONFLICT (date)
                DO UPDATE SET
                  market_status = EXCLUDED.market_status,
                  sp500_price = EXCLUDED.sp500_price,
                  sp500_change = EXCLUDED.sp500_change,
                  sp500_change_percent = EXCLUDED.sp500_change_percent,
                  nasdaq_price = EXCLUDED.nasdaq_price,
                  nasdaq_change = EXCLUDED.nasdaq_change,
                  nasdaq_change_percent = EXCLUDED.nasdaq_change_percent,
                  dow_price = EXCLUDED.dow_price,
                  dow_change = EXCLUDED.dow_change,
                  dow_change_percent = EXCLUDED.dow_change_percent,
                  total_volume = EXCLUDED.total_volume,
                  advancing_stocks = EXCLUDED.advancing_stocks,
                  declining_stocks = EXCLUDED.declining_stocks,
                  unchanged_stocks = EXCLUDED.unchanged_stocks
            """
            
            sp500 = indices.get('sp500', {})
            nasdaq = indices.get('nasdaq', {})
            dow = indices.get('dow', {})
            
            db.execute_update(query, {
                "date": snapshot_date.isoformat(),
                "market_status": overview.get('market_status', 'closed'),
                "sp500_price": sp500.get('price') if sp500 else None,
                "sp500_change": sp500.get('change') if sp500 else None,
                "sp500_change_percent": sp500.get('change_percent') if sp500 else None,
                "nasdaq_price": nasdaq.get('price') if nasdaq else None,
                "nasdaq_change": nasdaq.get('change') if nasdaq else None,
                "nasdaq_change_percent": nasdaq.get('change_percent') if nasdaq else None,
                "dow_price": dow.get('price') if dow else None,
                "dow_change": dow.get('change') if dow else None,
                "dow_change_percent": dow.get('change_percent') if dow else None,
                "total_volume": stats.get('total_volume', 0),
                "advancing": stats.get('advancing', 0),
                "declining": stats.get('declining', 0),
                "unchanged": stats.get('unchanged', 0)
            })
            
        except Exception as e:
            logger.error(f"Error saving market overview: {e}", exc_info=True)
            # Don't raise - this is non-critical

