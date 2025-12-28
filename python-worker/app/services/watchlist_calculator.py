"""
Watchlist Calculator Service
Calculates and updates all watchlist item metrics
Industry Standard: Comprehensive watchlist analytics
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, date
import json

from app.database import db
from app.data_sources import get_data_source
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors


class WatchlistCalculatorService(BaseService):
    """
    Calculates and updates watchlist item metrics
    
    Responsibilities:
    - Update current prices for watchlist items
    - Calculate price changes since added
    - Update sector/industry data
    - Fetch earnings dates
    - Calculate watchlist performance metrics
    
    SOLID: Single Responsibility - only calculates watchlist metrics
    """
    
    def __init__(self):
        """Initialize watchlist calculator service"""
        super().__init__()
        self.data_source = get_data_source()
    
    def update_watchlist_item_metrics(self, item_id: str) -> bool:
        """
        Update all metrics for a single watchlist item
        
        Args:
            item_id: Watchlist item ID to update
        
        Returns:
            True if successful
        """
        try:
            # Get watchlist item
            query = """
                SELECT wi.*, w.user_id
                FROM watchlist_items wi
                JOIN watchlists w ON wi.watchlist_id = w.watchlist_id
                WHERE wi.item_id = :item_id
            """
            items = db.execute_query(query, {"item_id": item_id})
            
            if not items:
                raise ValidationError(f"Watchlist item {item_id} not found")
            
            item = items[0]
            symbol = item['stock_symbol']
            
            # Fetch current price
            current_price = self.data_source.fetch_current_price(symbol)
            if current_price is None:
                self.log_warning(f"Could not fetch current price for {symbol}", context={'symbol': symbol})
                return False
            
            # Fetch fundamentals for sector/industry/dividend
            fundamentals = self.data_source.fetch_fundamentals(symbol)
            
            # Fetch earnings data
            earnings_data = self.data_source.fetch_earnings(symbol)
            next_earnings_date = None
            if earnings_data:
                # Get next earnings date
                today = date.today()
                for earning in earnings_data:
                    # Try different date fields
                    earnings_date_str = earning.get('earnings_date') or earning.get('date')
                    if earnings_date_str:
                        try:
                            # Handle different date formats
                            if isinstance(earnings_date_str, str):
                                if 'T' in earnings_date_str:
                                    earnings_date = datetime.fromisoformat(earnings_date_str.replace('Z', '+00:00')).date()
                                else:
                                    earnings_date = datetime.strptime(earnings_date_str, '%Y-%m-%d').date()
                            elif isinstance(earnings_date_str, datetime):
                                earnings_date = earnings_date_str.date()
                            else:
                                continue
                            
                            if earnings_date >= today:
                                next_earnings_date = earnings_date.isoformat()
                                break
                        except Exception as e:
                            logger.debug(f"Could not parse earnings date: {earnings_date_str}, error: {e}")
                            continue
            
            # Get or set price_when_added
            price_when_added = item.get('price_when_added')
            
            # If price_when_added is not set, set it to current price (first time)
            if not price_when_added or price_when_added == 0:
                price_when_added = current_price
            
            # Always calculate price change since added (will be 0 on first update)
            price_change_since_added = current_price - price_when_added
            price_change_percent_since_added = (price_change_since_added / price_when_added * 100) if price_when_added > 0 else 0
            
            # Extract sector/industry from fundamentals
            sector = fundamentals.get('sector') or fundamentals.get('industry')
            industry = fundamentals.get('industry')
            market_cap = fundamentals.get('marketCap', 0)
            dividend_yield = fundamentals.get('dividendYield', 0)
            
            # Determine market cap category
            market_cap_category = self._get_market_cap_category(market_cap)
            
            # Update watchlist item
            update_query = """
                UPDATE watchlist_items SET
                    current_price = :current_price,
                    price_when_added = :price_when_added,
                    price_change_since_added = :price_change_since_added,
                    price_change_percent_since_added = :price_change_percent_since_added,
                    sector = :sector,
                    industry = :industry,
                    market_cap_category = :market_cap_category,
                    dividend_yield = :dividend_yield,
                    earnings_date = :earnings_date,
                    last_updated_price = CURRENT_TIMESTAMP
                WHERE item_id = :item_id
            """
            
            db.execute_update(update_query, {
                "item_id": item_id,
                "current_price": current_price,
                "price_when_added": price_when_added,
                "price_change_since_added": price_change_since_added,
                "price_change_percent_since_added": price_change_percent_since_added,
                "sector": sector,
                "industry": industry,
                "market_cap_category": market_cap_category,
                "dividend_yield": dividend_yield * 100 if dividend_yield else None,  # Convert to percentage
                "earnings_date": next_earnings_date
            })
            
            self.log_info(f"✅ Updated metrics for watchlist item {item_id} ({symbol})", 
                         context={'item_id': item_id, 'symbol': symbol})
            return True
            
        except Exception as e:
            self.log_error(f"Error updating watchlist item metrics for {item_id}", e, 
                          context={'item_id': item_id, 'symbol': symbol})
            raise DatabaseError(f"Failed to update watchlist item metrics: {str(e)}") from e
    
    def update_watchlist_items(self, watchlist_id: str) -> int:
        """
        Update all items in a watchlist
        
        Args:
            watchlist_id: Watchlist ID
        
        Returns:
            Number of items updated
        """
        # Get all items
        query = "SELECT item_id FROM watchlist_items WHERE watchlist_id = :watchlist_id"
        items = db.execute_query(query, {"watchlist_id": watchlist_id})
        
        updated_count = 0
        for item in items:
            try:
                if self.update_watchlist_item_metrics(item['item_id']):
                    updated_count += 1
            except Exception as e:
                self.log_error(f"Error updating watchlist item {item['item_id']}", e, 
                              context={'item_id': item['item_id'], 'symbol': item.get('stock_symbol')})
                # Continue with other items (fail-fast per item, not all)
        
        return updated_count
    
    def calculate_watchlist_performance(self, watchlist_id: str, snapshot_date: date = None) -> Dict[str, Any]:
        """
        Calculate watchlist performance snapshot
        
        Args:
            watchlist_id: Watchlist ID
            snapshot_date: Date for snapshot (default: today)
        
        Returns:
            Performance metrics dictionary
        """
        if snapshot_date is None:
            snapshot_date = date.today()
        
        try:
            # Get all items
            query = """
                SELECT * FROM watchlist_items 
                WHERE watchlist_id = :watchlist_id
            """
            items = db.execute_query(query, {"watchlist_id": watchlist_id})
            
            if not items:
                return {
                    "total_stocks": 0,
                    "avg_price_change": 0,
                    "avg_price_change_percent": 0
                }
            
            # Calculate averages
            price_changes = [item.get('price_change_since_added') or 0 for item in items if item.get('price_change_since_added') is not None]
            price_change_percents = [item.get('price_change_percent_since_added') or 0 for item in items if item.get('price_change_percent_since_added') is not None]
            
            avg_price_change = sum(price_changes) / len(price_changes) if price_changes else 0
            avg_price_change_percent = sum(price_change_percents) / len(price_change_percents) if price_change_percents else 0
            
            # Count by trend (would need indicators, simplified for now)
            # Only count items with valid price_change_percent_since_added (not None)
            bullish_count = sum(1 for item in items 
                              if item.get('price_change_percent_since_added') is not None 
                              and item.get('price_change_percent_since_added', 0) > 5)
            bearish_count = sum(1 for item in items 
                              if item.get('price_change_percent_since_added') is not None 
                              and item.get('price_change_percent_since_added', 0) < -5)
            neutral_count = len(items) - bullish_count - bearish_count
            
            # Calculate sector distribution
            sector_distribution = {}
            for item in items:
                sector = item.get('sector') or 'Unknown'
                sector_distribution[sector] = sector_distribution.get(sector, 0) + 1
            
            # Get top gainers and losers
            items_sorted = sorted(
                items,
                key=lambda i: i.get('price_change_percent_since_added') or 0,
                reverse=True
            )
            top_gainers = [
                {
                    "symbol": item['stock_symbol'],
                    "change_percent": item.get('price_change_percent_since_added') or 0
                }
                for item in items_sorted[:5] if item.get('price_change_percent_since_added', 0) > 0
            ]
            top_losers = [
                {
                    "symbol": item['stock_symbol'],
                    "change_percent": item.get('price_change_percent_since_added') or 0
                }
                for item in reversed(items_sorted[-5:]) if item.get('price_change_percent_since_added', 0) < 0
            ]
            
            # Save snapshot
            query = """
                INSERT OR REPLACE INTO watchlist_performance
                (watchlist_id, snapshot_date, total_stocks, avg_price_change, avg_price_change_percent,
                 bullish_count, bearish_count, neutral_count, sector_distribution, top_gainers, top_losers)
                VALUES (:watchlist_id, :snapshot_date, :total_stocks, :avg_price_change, :avg_price_change_percent,
                        :bullish_count, :bearish_count, :neutral_count, :sector_distribution, :top_gainers, :top_losers)
            """
            
            db.execute_update(query, {
                "watchlist_id": watchlist_id,
                "snapshot_date": snapshot_date.isoformat(),
                "total_stocks": len(items),
                "avg_price_change": avg_price_change,
                "avg_price_change_percent": avg_price_change_percent,
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
                "sector_distribution": json.dumps(sector_distribution),
                "top_gainers": json.dumps(top_gainers),
                "top_losers": json.dumps(top_losers)
            })
            
            return {
                "total_stocks": len(items),
                "avg_price_change": avg_price_change,
                "avg_price_change_percent": avg_price_change_percent,
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count,
                "sector_distribution": sector_distribution,
                "top_gainers": top_gainers,
                "top_losers": top_losers
            }
            
        except Exception as e:
            self.log_error("Error calculating watchlist performance", e, context={'watchlist_id': watchlist_id})
            raise DatabaseError(f"Failed to calculate watchlist performance: {str(e)}", details={'watchlist_id': watchlist_id}) from e
    
    def _get_market_cap_category(self, market_cap: float) -> Optional[str]:
        """Determine market cap category"""
        if not market_cap or market_cap == 0:
            return None
        
        # Market cap in billions
        market_cap_b = market_cap / 1_000_000_000
        
        if market_cap_b >= 200:
            return 'mega'
        elif market_cap_b >= 10:
            return 'large'
        elif market_cap_b >= 2:
            return 'mid'
        elif market_cap_b >= 0.3:
            return 'small'
        else:
            return 'micro'

