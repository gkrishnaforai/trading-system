"""
Rating Update Service
Handles rating and price target updates for subscribed symbols
Follows SOLID principles: Single Responsibility, Dependency Inversion
"""

import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
import asyncio

from app.services.alert_subscription_service import alert_subscription_service
from app.services.data_sources.fmp import FMPDataSource
from app.database import db
from app.observability.logging import get_logger

logger = get_logger("rating_update_service")


@dataclass
class RatingUpdateResult:
    """Result of rating update operation"""
    symbol: str
    success: bool
    old_rating: Optional[str] = None
    new_rating: Optional[str] = None
    old_price_target: Optional[float] = None
    new_price_target: Optional[float] = None
    consensus_score: Optional[float] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None


class RatingUpdateService:
    """Service for updating ratings and price targets"""
    
    def __init__(self):
        self.fmp_data_source = FMPDataSource()
        self._batch_size = 50  # Process 50 symbols at a time
        self._rate_limit_delay = 1.0  # 1 second between batches
    
    async def process_rating_updates(self, symbols: List[str] = None) -> List[RatingUpdateResult]:
        """Process rating updates for subscribed symbols"""
        try:
            # Get symbols subscribed to rating updates
            if symbols is None:
                symbols = await alert_subscription_service.get_symbols_for_alert_type('rating_updates')
            
            if not symbols:
                logger.info("📋 No symbols subscribed to rating updates")
                return []
            
            logger.info(f"🔄 Processing rating updates for {len(symbols)} symbols")
            
            results = []
            # Process in batches to respect rate limits
            for i in range(0, len(symbols), self._batch_size):
                batch = symbols[i:i + self._batch_size]
                batch_results = await self._process_batch(batch)
                results.extend(batch_results)
                
                # Rate limiting delay
                if i + self._batch_size < len(symbols):
                    await asyncio.sleep(self._rate_limit_delay)
            
            # Log summary
            successful = sum(1 for r in results if r.success)
            logger.info(f"✅ Rating updates complete: {successful}/{len(results)} successful")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error processing rating updates: {e}")
            return []
    
    async def _process_batch(self, symbols: List[str]) -> List[RatingUpdateResult]:
        """Process a batch of symbols"""
        results = []
        
        for symbol in symbols:
            try:
                result = await self._update_symbol_ratings(symbol)
                results.append(result)
                
                # Small delay between individual requests
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"❌ Error updating {symbol}: {e}")
                results.append(RatingUpdateResult(
                    symbol=symbol,
                    success=False,
                    error_message=str(e),
                    processed_at=datetime.now()
                ))
        
        return results
    
    async def _update_symbol_ratings(self, symbol: str) -> RatingUpdateResult:
        """Update ratings for a single symbol"""
        try:
            # Get current data from stocks table
            current_data = await self._get_current_stock_data(symbol)
            
            # Fetch latest consensus data from FMP
            consensus_data = await self.fmp_data_source.get_consensus_data(symbol)
            price_target_data = await self.fmp_data_source.get_price_target_consensus(symbol)
            
            if not consensus_data and not price_target_data:
                return RatingUpdateResult(
                    symbol=symbol,
                    success=False,
                    error_message="No data available from FMP",
                    processed_at=datetime.now()
                )
            
            # Determine new values
            new_rating = None
            new_price_target = None
            consensus_score = None
            
            if consensus_data:
                new_rating = consensus_data.get('consensus_rating')
                consensus_score = consensus_data.get('consensus_score')
            
            if price_target_data:
                new_price_target = price_target_data.get('target_mean')
            
            # Check if updates are needed
            rating_changed = current_data.get('rating') != new_rating
            price_target_changed = current_data.get('price_target') != new_price_target
            
            if not rating_changed and not price_target_changed:
                logger.debug(f"📋 No changes for {symbol}")
                return RatingUpdateResult(
                    symbol=symbol,
                    success=True,
                    old_rating=current_data.get('rating'),
                    new_rating=new_rating,
                    old_price_target=current_data.get('price_target'),
                    new_price_target=new_price_target,
                    consensus_score=consensus_score,
                    processed_at=datetime.now()
                )
            
            # Update stocks table
            await self._update_stocks_table(symbol, new_rating, new_price_target, consensus_score)
            
            # Log the change
            await self._log_rating_change(
                symbol, current_data, new_rating, new_price_target, consensus_score
            )
            
            logger.info(f"✅ Updated {symbol}: rating={current_data.get('rating')}→{new_rating}, "
                       f"price_target={current_data.get('price_target')}→{new_price_target}")
            
            return RatingUpdateResult(
                symbol=symbol,
                success=True,
                old_rating=current_data.get('rating'),
                new_rating=new_rating,
                old_price_target=current_data.get('price_target'),
                new_price_target=new_price_target,
                consensus_score=consensus_score,
                processed_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"❌ Error updating {symbol}: {e}")
            return RatingUpdateResult(
                symbol=symbol,
                success=False,
                error_message=str(e),
                processed_at=datetime.now()
            )
    
    async def _get_current_stock_data(self, symbol: str) -> Dict[str, Any]:
        """Get current rating and price target from stocks table"""
        try:
            query = """
                SELECT rating, price_target, rating_updated_at 
                FROM stocks 
                WHERE symbol = $1
            """

            rows = db.execute_query_positional(query, [symbol])
            
            if rows:
                return {
                    'rating': rows[0].get('rating'),
                    'price_target': rows[0].get('price_target'),
                    'rating_updated_at': rows[0].get('rating_updated_at'),
                }
            else:
                return {}
                
        except Exception as e:
            logger.error(f"❌ Error getting current data for {symbol}: {e}")
            return {}
    
    async def _update_stocks_table(self, symbol: str, rating: str = None, 
                                 price_target: float = None, consensus_score: float = None):
        """Update stocks table with new rating data"""
        try:
            # Build update query dynamically
            updates = []
            params = []
            
            if rating is not None:
                updates.append("rating = %s")
                params.append(rating)
            
            if price_target is not None:
                updates.append("price_target = %s")
                params.append(price_target)
            
            if consensus_score is not None:
                updates.append("rating_score = %s")
                params.append(consensus_score)
            
            updates.append("rating_updated_at = %s")
            params.append(datetime.now())
            params.append(symbol)
            
            if updates:
                query = f"""
                    UPDATE stocks 
                    SET {', '.join(updates)}
                    WHERE symbol = %s
                """
                
                db.execute_update(query, params)
                
        except Exception as e:
            logger.error(f"❌ Error updating stocks table for {symbol}: {e}")
            raise
    
    async def _log_rating_change(self, symbol: str, old_data: Dict[str, Any], 
                               new_rating: str = None, new_price_target: float = None,
                               consensus_score: float = None):
        """Log rating change for audit trail"""
        try:
            # Check if this is a significant change
            rating_changed = old_data.get('rating') != new_rating
            price_target_changed = old_data.get('price_target') != new_price_target
            
            if not rating_changed and not price_target_changed:
                return
            
            # Insert into rating change log
            query = """
                INSERT INTO rating_change_log (
                    symbol, old_rating, new_rating, old_price_target, new_price_target,
                    consensus_score, change_type, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            change_type = []
            if rating_changed:
                change_type.append('rating')
            if price_target_changed:
                change_type.append('price_target')
            
            params = [
                symbol,
                old_data.get('rating'),
                new_rating,
                old_data.get('price_target'),
                new_price_target,
                consensus_score,
                ','.join(change_type),
                datetime.now()
            ]
            
            db.execute_update(query, params)
            
        except Exception as e:
            logger.error(f"❌ Error logging rating change for {symbol}: {e}")
    
    async def get_update_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get rating update statistics"""
        try:
            query = """
                SELECT 
                    COUNT(*) as total_updates,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(*) FILTER (WHERE change_type LIKE '%rating%') as rating_updates,
                    COUNT(*) FILTER (WHERE change_type LIKE '%price_target%') as price_target_updates,
                    AVG(consensus_score) as avg_consensus_score,
                    MAX(created_at) as last_update
                FROM rating_change_log 
                WHERE created_at >= NOW() - make_interval(days => $1)
            """

            rows = db.execute_query_positional(query, [days])
            
            if rows:
                return {
                    'total_updates': rows[0].get('total_updates'),
                    'unique_symbols': rows[0].get('unique_symbols'),
                    'rating_updates': rows[0].get('rating_updates'),
                    'price_target_updates': rows[0].get('price_target_updates'),
                    'avg_consensus_score': float(rows[0].get('avg_consensus_score')) if rows[0].get('avg_consensus_score') else None,
                    'last_update': rows[0].get('last_update'),
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error getting update statistics: {e}")
            return {}


# Global service instance
rating_update_service = RatingUpdateService()
