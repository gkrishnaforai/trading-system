"""
Rating Service - Core rating and price target management
Follows SOLID principles: Single Responsibility, Dependency Inversion
"""

import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import json

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("rating_service")


@dataclass
class RatingData:
    """Rating data structure"""
    symbol: str
    rating: Optional[str] = None
    price_target: Optional[float] = None
    rating_score: Optional[float] = None
    consensus_data: Optional[Dict[str, Any]] = None
    data_source: str = 'fmp'
    updated_at: Optional[datetime] = None


@dataclass
class RatingChange:
    """Rating change event"""
    symbol: str
    old_rating: Optional[str]
    new_rating: Optional[str]
    old_price_target: Optional[float]
    new_price_target: Optional[float]
    rating_score: Optional[float]
    change_type: str  # 'rating', 'price_target', 'both', 'consensus'
    consensus_data: Optional[Dict[str, Any]] = None
    data_source: str = 'fmp'
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class RatingRepository(ABC):
    """Abstract repository for rating data"""
    
    @abstractmethod
    async def get_current_rating(self, symbol: str) -> Optional[RatingData]:
        """Get current rating data for a symbol"""
        pass
    
    @abstractmethod
    async def update_rating(self, rating_data: RatingData) -> bool:
        """Update rating data for a symbol"""
        pass
    
    @abstractmethod
    async def log_rating_change(self, change: RatingChange) -> bool:
        """Log a rating change event"""
        pass
    
    @abstractmethod
    async def get_rating_history(self, symbol: str, days: int = 30) -> List[RatingChange]:
        """Get rating change history for a symbol"""
        pass


class PostgresRatingRepository(RatingRepository):
    """PostgreSQL implementation of rating repository"""
    
    async def get_current_rating(self, symbol: str) -> Optional[RatingData]:
        """Get current rating data from stocks table"""
        try:
            query = """
                SELECT rating, price_target, rating_score, rating_updated_at, rating_data_source
                FROM stocks 
                WHERE symbol = $1
            """

            rows = db.execute_query_positional(query, [symbol])
            
            if rows:
                row = rows[0]
                return RatingData(
                    symbol=symbol,
                    rating=row.get("rating"),
                    price_target=row.get("price_target"),
                    rating_score=row.get("rating_score"),
                    data_source=row.get("rating_data_source") or 'fmp',
                    updated_at=row.get("rating_updated_at"),
                )
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting current rating for {symbol}: {e}")
            return None
    
    async def update_rating(self, rating_data: RatingData) -> bool:
        """Update rating data in stocks table"""
        try:
            query = """
                UPDATE stocks 
                SET rating = %s, price_target = %s, rating_score = %s, 
                    rating_updated_at = %s, rating_data_source = %s, updated_at = %s
                WHERE symbol = %s
            """
            
            params = [
                rating_data.rating,
                rating_data.price_target,
                rating_data.rating_score,
                datetime.now(),
                rating_data.data_source,
                rating_data.symbol
            ]
            
            result = db.execute_update(query, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ Error updating rating for {rating_data.symbol}: {e}")
            return False
    
    async def log_rating_change(self, change: RatingChange) -> bool:
        """Log rating change to rating_change_log table"""
        try:
            query = """
                INSERT INTO rating_change_log (
                    symbol, old_rating, new_rating, old_price_target, new_price_target,
                    rating_score, consensus_data, change_type, data_source, processed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            params = [
                change.symbol,
                change.old_rating,
                change.new_rating,
                change.old_price_target,
                change.new_price_target,
                change.rating_score,
                json.dumps(change.consensus_data) if change.consensus_data else None,
                change.change_type,
                change.data_source,
                change.created_at
            ]
            
            result = db.execute_update(query, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ Error logging rating change for {change.symbol}: {e}")
            return False
    
    async def get_rating_history(self, symbol: str, days: int = 30) -> List[RatingChange]:
        """Get rating change history for a symbol"""
        try:
            query = """
                SELECT symbol, old_rating, new_rating, old_price_target, new_price_target,
                       rating_score, consensus_data, change_type, data_source, created_at
                FROM rating_change_log 
                WHERE symbol = $1 AND created_at >= NOW() - make_interval(days => $2)
                ORDER BY created_at DESC
            """

            rows = db.execute_query_positional(query, [symbol, days])
            
            changes = []
            for row in rows:
                consensus_data = json.loads(row.get("consensus_data")) if row.get("consensus_data") else None
                
                change = RatingChange(
                    symbol=row.get("symbol"),
                    old_rating=row.get("old_rating"),
                    new_rating=row.get("new_rating"),
                    old_price_target=row.get("old_price_target"),
                    new_price_target=row.get("new_price_target"),
                    rating_score=row.get("rating_score"),
                    consensus_data=consensus_data,
                    change_type=row.get("change_type"),
                    data_source=row.get("data_source"),
                    created_at=row.get("created_at"),
                )
                changes.append(change)
            
            return changes
            
        except Exception as e:
            logger.error(f"❌ Error getting rating history for {symbol}: {e}")
            return []


class RatingDataSource(ABC):
    """Abstract data source for rating data"""
    
    @abstractmethod
    async def get_consensus_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus rating data"""
        pass
    
    @abstractmethod
    async def get_price_target_consensus(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get price target consensus data"""
        pass


class FMPRatingDataSource(RatingDataSource):
    """FMP implementation of rating data source"""
    
    def __init__(self):
        from app.services.data_sources.fmp import FMPDataSource
        self.fmp_data_source = FMPDataSource()
    
    async def get_consensus_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get consensus rating data from FMP"""
        try:
            consensus_data = await self.fmp_data_source.get_consensus_data(symbol)
            return consensus_data
        except Exception as e:
            logger.error(f"❌ Error getting consensus data from FMP for {symbol}: {e}")
            return None
    
    async def get_price_target_consensus(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get price target consensus data from FMP"""
        try:
            price_target_data = await self.fmp_data_source.get_price_target_consensus(symbol)
            return price_target_data
        except Exception as e:
            logger.error(f"❌ Error getting price target data from FMP for {symbol}: {e}")
            return None


class RatingService:
    """Main rating service - follows Single Responsibility Principle"""
    
    def __init__(self, repository: RatingRepository = None, data_source: RatingDataSource = None):
        self.repository = repository or PostgresRatingRepository()
        self.data_source = data_source or FMPRatingDataSource()
    
    async def update_symbol_ratings(self, symbol: str) -> Optional[RatingChange]:
        """Update ratings for a single symbol"""
        try:
            logger.info(f"🔄 Updating ratings for {symbol}")
            
            # Get current data
            current_data = await self.repository.get_current_rating(symbol)
            
            # Fetch latest data from data source
            consensus_data = await self.data_source.get_consensus_data(symbol)
            price_target_data = await self.data_source.get_price_target_consensus(symbol)
            
            if not consensus_data and not price_target_data:
                logger.warning(f"⚠️ No data available for {symbol}")
                return None
            
            # Extract new values
            new_rating = consensus_data.get('consensus_rating') if consensus_data else None
            new_price_target = price_target_data.get('target_mean') if price_target_data else None
            rating_score = consensus_data.get('consensus_score') if consensus_data else None
            
            # Check if changes are needed
            rating_changed = current_data.rating != new_rating if current_data else new_rating is not None
            price_target_changed = current_data.price_target != new_price_target if current_data else new_price_target is not None
            
            if not rating_changed and not price_target_changed:
                logger.debug(f"📋 No changes for {symbol}")
                return None
            
            # Determine change type
            if rating_changed and price_target_changed:
                change_type = 'both'
            elif rating_changed:
                change_type = 'rating'
            elif price_target_changed:
                change_type = 'price_target'
            else:
                change_type = 'consensus'
            
            # Create rating change event
            change = RatingChange(
                symbol=symbol,
                old_rating=current_data.rating if current_data else None,
                new_rating=new_rating,
                old_price_target=current_data.price_target if current_data else None,
                new_price_target=new_price_target,
                rating_score=rating_score,
                change_type=change_type,
                consensus_data=consensus_data,
                data_source='fmp'
            )
            
            # Update stocks table
            rating_data = RatingData(
                symbol=symbol,
                rating=new_rating,
                price_target=new_price_target,
                rating_score=rating_score,
                consensus_data=consensus_data,
                data_source='fmp'
            )
            
            update_success = await self.repository.update_rating(rating_data)
            if not update_success:
                logger.error(f"❌ Failed to update rating data for {symbol}")
                return None
            
            # Log the change
            log_success = await self.repository.log_rating_change(change)
            if not log_success:
                logger.warning(f"⚠️ Failed to log rating change for {symbol}")
            
            logger.info(f"✅ Updated {symbol}: {change_type} change")
            return change
            
        except Exception as e:
            logger.error(f"❌ Error updating ratings for {symbol}: {e}")
            return None
    
    async def batch_update_ratings(self, symbols: List[str]) -> List[RatingChange]:
        """Update ratings for multiple symbols"""
        changes = []
        
        for symbol in symbols:
            try:
                change = await self.update_symbol_ratings(symbol)
                if change:
                    changes.append(change)
                
                # Small delay to respect rate limits
                import asyncio
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"❌ Error in batch update for {symbol}: {e}")
        
        logger.info(f"📊 Batch update complete: {len(changes)} changes for {len(symbols)} symbols")
        return changes
    
    async def get_rating_summary(self, symbol: str) -> Dict[str, Any]:
        """Get rating summary for a symbol"""
        try:
            current_data = await self.repository.get_current_rating(symbol)
            history = await self.repository.get_rating_history(symbol, days=30)
            
            return {
                'symbol': symbol,
                'current': asdict(current_data) if current_data else None,
                'history': [asdict(change) for change in history],
                'recent_changes': len([h for h in history if h.created_at >= datetime.now() - timedelta(days=7)]),
                'last_updated': current_data.updated_at if current_data else None
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting rating summary for {symbol}: {e}")
            return {}
    
    async def get_recent_changes(self, days: int = 7) -> Dict[str, Any]:
        """Get rating update statistics"""
        try:
            query = """
                SELECT COUNT(*) as total_changes
                FROM rating_change_log
                WHERE created_at >= NOW() - make_interval(days => $1)
            """

            rows = db.execute_query_positional(query, [days])
            
            if rows:
                return {"total_changes": rows[0].get("total_changes"), "period_days": days}
            
            return {
                "total_changes": 0,
                "period_days": days
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting recent changes: {e}")
            return {}
    
    async def get_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get rating update statistics"""
        try:
            query = """
                SELECT 
                    COUNT(*) as total_changes,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(*) FILTER (WHERE change_type = 'rating') as rating_changes,
                    COUNT(*) FILTER (WHERE change_type = 'price_target') as price_target_changes,
                    COUNT(*) FILTER (WHERE change_type = 'both') as both_changes,
                    AVG(rating_score) as avg_rating_score,
                    MAX(created_at) as last_update
                FROM rating_change_log 
                WHERE created_at >= NOW() - make_interval(days => $1)
            """
            
            rows = db.execute_query_positional(query, [days])
            
            if rows:
                return {
                    'total_changes': rows[0].get("total_changes"),
                    'unique_symbols': rows[0].get("unique_symbols"),
                    'rating_changes': rows[0].get("rating_changes"),
                    'price_target_changes': rows[0].get("price_target_changes"),
                    'both_changes': rows[0].get("both_changes"),
                    'avg_rating_score': float(rows[0].get("avg_rating_score")) if rows[0].get("avg_rating_score") else None,
                    'last_update': rows[0].get("last_update")
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"❌ Error getting statistics: {e}")
            return {}


# Global service instance
rating_service = RatingService()
