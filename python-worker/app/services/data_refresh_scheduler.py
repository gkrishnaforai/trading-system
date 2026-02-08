"""
Data Refresh Scheduler Service
Handles automated data refresh scheduling using database triggers and background tasks
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import text
from app.database import db
from app.observability.logging import get_logger

logger = get_logger("data_refresh_scheduler")

class DataRefreshScheduler:
    """Service for managing automated data refresh scheduling"""
    
    def __init__(self):
        self.is_running = False
        self.refresh_intervals = {
            'price_historical': 15,  # minutes
            'indicators': 30,        # minutes
            'fundamentals': 60,      # minutes
            'earnings': 240,         # minutes (4 hours)
        }
    
    async def start_scheduler(self):
        """Start the background scheduler"""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        self.is_running = True
        logger.info("🚀 Starting data refresh scheduler")
        
        # Create scheduler table if not exists
        await self.create_scheduler_table()
        
        # Start background task
        asyncio.create_task(self.scheduler_loop())
    
    async def stop_scheduler(self):
        """Stop the background scheduler"""
        self.is_running = False
        logger.info("⏹️ Data refresh scheduler stopped")
    
    async def create_scheduler_table(self):
        """Create table for tracking scheduled refreshes"""
        try:
            create_table_query = """
            CREATE TABLE IF NOT EXISTS data_refresh_schedule (
                id SERIAL PRIMARY KEY,
                data_type VARCHAR(50) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                last_refresh TIMESTAMP,
                next_refresh TIMESTAMP,
                refresh_interval INTEGER NOT NULL,  -- minutes
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, data_type)
            );
            
            CREATE INDEX IF NOT EXISTS idx_refresh_schedule_next_refresh 
            ON data_refresh_schedule(next_refresh, is_active);
            
            CREATE INDEX IF NOT EXISTS idx_refresh_schedule_symbol 
            ON data_refresh_schedule(symbol);
            """
            
            db.execute_update(create_table_query)
            logger.info("✅ Data refresh schedule table created/verified")
            
        except Exception as e:
            logger.error(f"❌ Error creating scheduler table: {e}")
            raise
    
    async def schedule_symbol_refresh(self, symbol: str, data_types: List[str] = None):
        """Schedule a symbol for automatic refresh"""
        if data_types is None:
            data_types = ['price_historical', 'indicators', 'fundamentals', 'earnings']
        
        try:
            current_time = datetime.now()
            
            for data_type in data_types:
                if data_type not in self.refresh_intervals:
                    logger.warning(f"Unknown data type: {data_type}")
                    continue
                
                interval = self.refresh_intervals[data_type]
                next_refresh = current_time + timedelta(minutes=interval)
                
                # Upsert schedule record
                upsert_query = """
                INSERT INTO data_refresh_schedule 
                (symbol, data_type, last_refresh, next_refresh, refresh_interval, is_active)
                VALUES (:symbol, :data_type, :last_refresh, :next_refresh, :interval, :is_active)
                ON CONFLICT (symbol, data_type) 
                DO UPDATE SET
                    next_refresh = EXCLUDED.next_refresh,
                    refresh_interval = EXCLUDED.refresh_interval,
                    is_active = EXCLUDED.is_active,
                    updated_at = CURRENT_TIMESTAMP
                """
                
                db.execute_update(upsert_query, {
                    'symbol': symbol.upper(),
                    'data_type': data_type,
                    'last_refresh': current_time,
                    'next_refresh': next_refresh,
                    'interval': interval,
                    'is_active': True
                })
            
            logger.info(f"✅ Scheduled refresh for {symbol}: {data_types}")
            
        except Exception as e:
            logger.error(f"❌ Error scheduling refresh for {symbol}: {e}")
            raise
    
    async def scheduler_loop(self):
        """Main scheduler loop - runs in background"""
        logger.info("🔄 Scheduler loop started")
        
        while self.is_running:
            try:
                # Check for due refreshes
                await self.process_due_refreshes()
                
                # Sleep for 1 minute before next check
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"❌ Error in scheduler loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def process_due_refreshes(self):
        """Process all refreshes that are due"""
        try:
            current_time = datetime.now()
            
            # Get due refreshes
            due_query = """
            SELECT symbol, data_type, refresh_interval
            FROM data_refresh_schedule
            WHERE is_active = TRUE 
            AND next_refresh <= :current_time
            ORDER BY next_refresh ASC
            LIMIT 50
            """
            
            due_refreshes = db.execute_query(due_query, {
                'current_time': current_time
            })
            
            if not due_refreshes:
                return
            
            logger.info(f"🔄 Processing {len(due_refreshes)} due refreshes")
            
            # Group by data type for batch processing
            refresh_groups = {}
            for refresh in due_refreshes:
                data_type = refresh['data_type']
                if data_type not in refresh_groups:
                    refresh_groups[data_type] = []
                refresh_groups[data_type].append(refresh['symbol'])
            
            # Process each group
            for data_type, symbols in refresh_groups.items():
                await self.refresh_data_batch(symbols, [data_type])
                
                # Update next refresh time for these symbols
                interval = self.refresh_intervals.get(data_type, 60)
                next_refresh = current_time + timedelta(minutes=interval)
                
                update_query = """
                UPDATE data_refresh_schedule
                SET last_refresh = :current_time,
                    next_refresh = :next_refresh,
                    updated_at = CURRENT_TIMESTAMP
                WHERE symbol = ANY(:symbols)
                AND data_type = :data_type
                """
                
                db.execute_update(update_query, {
                    'current_time': current_time,
                    'next_refresh': next_refresh,
                    'symbols': symbols,
                    'data_type': data_type
                })
            
            logger.info(f"✅ Completed {len(due_refreshes)} refreshes")
            
        except Exception as e:
            logger.error(f"❌ Error processing due refreshes: {e}")
    
    async def refresh_data_batch(self, symbols: List[str], data_types: List[str]):
        """Refresh data for a batch of symbols"""
        try:
            # Import here to avoid circular imports
            from app.services.data_refresh_service import DataRefreshService
            
            refresh_service = DataRefreshService()
            
            # Process in smaller batches to respect rate limits
            batch_size = 5
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                
                success = await refresh_service.refresh_symbols_data(
                    symbols=batch,
                    data_types=data_types,
                    force=True
                )
                
                if success:
                    logger.info(f"✅ Refreshed {data_types} for {batch}")
                else:
                    logger.warning(f"⚠️ Failed to refresh {data_types} for {batch}")
                
                # Rate limiting delay
                if i + batch_size < len(symbols):
                    await asyncio.sleep(15)  # 15 seconds between batches
            
        except Exception as e:
            logger.error(f"❌ Error refreshing data batch: {e}")
    
    async def get_schedule_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        try:
            # Get total scheduled items
            total_query = """
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN is_active THEN 1 END) as active,
                   COUNT(CASE WHEN next_refresh <= NOW() THEN 1 END) as overdue
            FROM data_refresh_schedule
            """
            
            result = db.execute_query(total_query)
            stats = result[0] if result else {'total': 0, 'active': 0, 'overdue': 0}
            
            # Get next refresh time
            next_query = """
            SELECT MIN(next_refresh) as next_refresh
            FROM data_refresh_schedule
            WHERE is_active = TRUE
            """
            
            next_result = db.execute_query(next_query)
            next_refresh = next_result[0]['next_refresh'] if next_result else None
            
            return {
                'is_running': self.is_running,
                'total_scheduled': stats['total'],
                'active_schedules': stats['active'],
                'overdue_schedules': stats['overdue'],
                'next_refresh': next_refresh,
                'refresh_intervals': self.refresh_intervals
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting schedule status: {e}")
            return {
                'is_running': self.is_running,
                'total_scheduled': 0,
                'active_schedules': 0,
                'overdue_schedules': 0,
                'next_refresh': None,
                'refresh_intervals': self.refresh_intervals,
                'error': str(e)
            }
    
    async def remove_symbol_schedule(self, symbol: str, data_type: str = None):
        """Remove a symbol from refresh schedule"""
        try:
            if data_type:
                delete_query = """
                DELETE FROM data_refresh_schedule
                WHERE symbol = :symbol AND data_type = :data_type
                """
                db.execute_update(delete_query, {
                    'symbol': symbol.upper(),
                    'data_type': data_type
                })
            else:
                delete_query = """
                DELETE FROM data_refresh_schedule
                WHERE symbol = :symbol
                """
                db.execute_update(delete_query, {
                    'symbol': symbol.upper()
                })
            
            logger.info(f"✅ Removed schedule for {symbol}" + (f" ({data_type})" if data_type else ""))
            
        except Exception as e:
            logger.error(f"❌ Error removing schedule for {symbol}: {e}")
            raise

# Global scheduler instance
scheduler = DataRefreshScheduler()
