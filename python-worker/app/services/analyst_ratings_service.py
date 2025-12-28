"""
Analyst Ratings Service
Fetches and manages analyst ratings and consensus
Industry Standard: Analyst recommendations and price targets
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.data_sources.finnhub_source import FinnhubSource

logger = logging.getLogger(__name__)


class AnalystRatingsService(BaseService):
    """
    Service for managing analyst ratings and consensus
    
    SOLID: Single Responsibility - only handles analyst ratings
    """
    
    def __init__(self, data_source=None):
        """
        Initialize analyst ratings service
        
        Args:
            data_source: Data source for fetching ratings (default: Finnhub)
        """
        super().__init__()
        self.data_source = data_source or FinnhubSource()
    
    def fetch_and_save_ratings(self, symbol: str) -> int:
        """
        Fetch analyst ratings from data source and save to database
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Number of ratings saved
        """
        try:
            if not self.data_source.is_available():
                logger.warning(f"Analyst ratings data source not available for {symbol}")
                return 0
            
            # Fetch ratings from data source
            ratings = self.data_source.fetch_analyst_ratings(symbol)
            
            if not ratings:
                logger.warning(f"No analyst ratings found for {symbol}")
                return 0
            
            # Save to database
            saved_count = 0
            for rating in ratings:
                query = """
                    INSERT OR REPLACE INTO analyst_ratings
                    (stock_symbol, analyst_name, rating, price_target, rating_date, source)
                    VALUES (:symbol, :analyst_name, :rating, :price_target, :rating_date, :source)
                """
                db.execute_update(query, {
                    "symbol": symbol,
                    "analyst_name": rating.get('analyst_name', 'Unknown'),
                    "rating": rating.get('rating', 'hold'),
                    "price_target": rating.get('price_target'),
                    "rating_date": rating.get('rating_date'),
                    "source": rating.get('source', 'finnhub')
                })
                saved_count += 1
            
            # Update consensus
            self._update_consensus(symbol)
            
            logger.info(f"✅ Saved {saved_count} analyst ratings for {symbol}")
            return saved_count
            
        except Exception as e:
            logger.error(f"Error fetching and saving analyst ratings for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to fetch analyst ratings: {str(e)}") from e
    
    def get_analyst_ratings(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Get analyst ratings for a symbol from database
        
        Args:
            symbol: Stock symbol
        
        Returns:
            List of analyst ratings
        """
        try:
            query = """
                SELECT analyst_name, firm_name, rating, price_target, rating_date, source
                FROM analyst_ratings
                WHERE stock_symbol = :symbol
                ORDER BY rating_date DESC, analyst_name
            """
            result = db.execute_query(query, {"symbol": symbol})
            
            return [
                {
                    "analyst_name": r['analyst_name'],
                    "firm_name": r.get('firm_name'),
                    "rating": r['rating'],
                    "price_target": r.get('price_target'),
                    "rating_date": r.get('rating_date'),
                    "source": r.get('source', 'finnhub')
                }
                for r in result
            ]
            
        except Exception as e:
            logger.error(f"Error getting analyst ratings for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get analyst ratings: {str(e)}") from e
    
    def get_consensus(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get analyst consensus for a symbol
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Consensus data dictionary
        """
        try:
            query = """
                SELECT consensus_rating, consensus_price_target, strong_buy_count,
                       buy_count, hold_count, sell_count, strong_sell_count, total_ratings
                FROM analyst_consensus
                WHERE stock_symbol = :symbol
            """
            result = db.execute_query(query, {"symbol": symbol})
            
            if not result:
                # Calculate consensus if not exists
                self._update_consensus(symbol)
                result = db.execute_query(query, {"symbol": symbol})
            
            if result:
                return {
                    "symbol": symbol,
                    "consensus_rating": result[0]['consensus_rating'],
                    "consensus_price_target": result[0].get('consensus_price_target'),
                    "strong_buy_count": result[0]['strong_buy_count'],
                    "buy_count": result[0]['buy_count'],
                    "hold_count": result[0]['hold_count'],
                    "sell_count": result[0]['sell_count'],
                    "strong_sell_count": result[0]['strong_sell_count'],
                    "total_ratings": result[0]['total_ratings']
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting consensus for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to get consensus: {str(e)}") from e
    
    def _update_consensus(self, symbol: str):
        """Calculate and update analyst consensus"""
        try:
            # Get all ratings for symbol
            query = """
                SELECT rating, price_target
                FROM analyst_ratings
                WHERE stock_symbol = :symbol
            """
            ratings = db.execute_query(query, {"symbol": symbol})
            
            if not ratings:
                return
            
            # Count ratings
            strong_buy = sum(1 for r in ratings if r['rating'] == 'strong_buy')
            buy = sum(1 for r in ratings if r['rating'] == 'buy')
            hold = sum(1 for r in ratings if r['rating'] == 'hold')
            sell = sum(1 for r in ratings if r['rating'] == 'sell')
            strong_sell = sum(1 for r in ratings if r['rating'] == 'strong_sell')
            total = len(ratings)
            
            # Calculate consensus rating (weighted average)
            rating_scores = {
                'strong_buy': 5,
                'buy': 4,
                'hold': 3,
                'sell': 2,
                'strong_sell': 1
            }
            
            total_score = (
                strong_buy * rating_scores['strong_buy'] +
                buy * rating_scores['buy'] +
                hold * rating_scores['hold'] +
                sell * rating_scores['sell'] +
                strong_sell * rating_scores['strong_sell']
            )
            
            avg_score = total_score / total if total > 0 else 3
            
            if avg_score >= 4.5:
                consensus_rating = 'strong_buy'
            elif avg_score >= 3.5:
                consensus_rating = 'buy'
            elif avg_score >= 2.5:
                consensus_rating = 'hold'
            elif avg_score >= 1.5:
                consensus_rating = 'sell'
            else:
                consensus_rating = 'strong_sell'
            
            # Calculate average price target
            price_targets = [r['price_target'] for r in ratings if r.get('price_target')]
            consensus_price_target = sum(price_targets) / len(price_targets) if price_targets else None
            
            # Save consensus
            query = """
                INSERT OR REPLACE INTO analyst_consensus
                (stock_symbol, consensus_rating, consensus_price_target,
                 strong_buy_count, buy_count, hold_count, sell_count, strong_sell_count,
                 total_ratings, last_updated)
                VALUES (:symbol, :consensus_rating, :consensus_price_target,
                        :strong_buy, :buy, :hold, :sell, :strong_sell,
                        :total, CURRENT_TIMESTAMP)
            """
            db.execute_update(query, {
                "symbol": symbol,
                "consensus_rating": consensus_rating,
                "consensus_price_target": consensus_price_target,
                "strong_buy": strong_buy,
                "buy": buy,
                "hold": hold,
                "sell": sell,
                "strong_sell": strong_sell,
                "total": total
            })
            
        except Exception as e:
            logger.error(f"Error updating consensus for {symbol}: {e}", exc_info=True)
            # Don't raise - this is non-critical

