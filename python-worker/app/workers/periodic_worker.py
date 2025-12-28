"""
Periodic/Live data worker
Handles real-time and periodic data updates (current prices, news, etc.)
Runs in parallel with batch worker
"""
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import List

from app.config import settings
from app.database import db, init_database
from app.data_management.refresh_manager import DataRefreshManager
from app.data_management.refresh_strategy import RefreshMode, DataType

logger = logging.getLogger(__name__)


class PeriodicWorker:
    """Worker for periodic and live data updates"""
    
    def __init__(self):
        self.refresh_manager = DataRefreshManager()
        self.running = False
        self.thread = None
        
        # Define periodic refresh intervals
        self.periodic_intervals = {
            DataType.PRICE_CURRENT: timedelta(minutes=15),  # Every 15 minutes
            DataType.PRICE_INTRADAY_15M: timedelta(minutes=15),  # 15-minute candles
            DataType.NEWS: timedelta(hours=1),  # Every hour
            DataType.EARNINGS: timedelta(hours=6),  # Every 6 hours
            DataType.FUNDAMENTALS: timedelta(hours=12),  # Every 12 hours
        }
        
        # Define live refresh intervals (for real-time data)
        self.live_intervals = {
            DataType.PRICE_CURRENT: timedelta(minutes=1),  # Every minute
        }
    
    def start(self):
        """Start the periodic worker"""
        if self.running:
            logger.warning("Periodic worker is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("🔄 Periodic worker started")
    
    def stop(self):
        """Stop the periodic worker"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Periodic worker stopped")
    
    def _run_loop(self):
        """Main loop for periodic updates"""
        while self.running:
            try:
                # Run periodic updates
                self._run_periodic_updates()
                
                # Run live updates (if enabled)
                if settings.enable_live_updates:
                    self._run_live_updates()
                
                # Sleep for a short interval before next check
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in periodic worker loop: {e}")
                time.sleep(60)  # Wait before retrying
    
    def _run_periodic_updates(self):
        """Run periodic data updates"""
        symbols = self._get_active_symbols()
        
        for data_type, interval in self.periodic_intervals.items():
            try:
                # Get symbols that need refreshing
                symbols_to_refresh = self.refresh_manager.get_symbols_to_refresh(
                    data_type, RefreshMode.PERIODIC
                )
                
                if not symbols_to_refresh:
                    continue
                
                logger.info(f"🔄 Refreshing {data_type} for {len(symbols_to_refresh)} symbols (periodic)")
                
                for symbol in symbols_to_refresh[:10]:  # Limit to 10 at a time
                    try:
                        results = self.refresh_manager.refresh_data(
                            symbol=symbol,
                            data_types=[data_type],
                            mode=RefreshMode.PERIODIC,
                            force=False
                        )
                        dt_key = data_type.value if hasattr(data_type, "value") else str(data_type)
                        if results.results.get(dt_key) and results.results[dt_key].status.value == "success":
                            logger.debug(f"✅ Refreshed {data_type} for {symbol}")
                    except Exception as e:
                        logger.error(f"Error refreshing {data_type} for {symbol}: {e}")
                
            except Exception as e:
                logger.error(f"Error in periodic update for {data_type}: {e}")
    
    def _run_live_updates(self):
        """Run live/real-time data updates"""
        symbols = self._get_active_symbols()
        
        for data_type in self.live_intervals.keys():
            try:
                # Get symbols that need refreshing
                symbols_to_refresh = self.refresh_manager.get_symbols_to_refresh(
                    data_type, RefreshMode.LIVE
                )
                
                if not symbols_to_refresh:
                    continue
                
                # Limit live updates to prevent API rate limits
                for symbol in symbols_to_refresh[:5]:  # Only top 5 symbols
                    try:
                        results = self.refresh_manager.refresh_data(
                            symbol=symbol,
                            data_types=[data_type],
                            mode=RefreshMode.LIVE,
                            force=False
                        )
                        dt_key = data_type.value if hasattr(data_type, "value") else str(data_type)
                        if results.results.get(dt_key) and results.results[dt_key].status.value == "success":
                            logger.debug(f"⚡ Live update: {data_type} for {symbol}")
                    except Exception as e:
                        logger.error(f"Error in live update for {data_type} for {symbol}: {e}")
                
            except Exception as e:
                logger.error(f"Error in live update for {data_type}: {e}")
    
    def _get_active_symbols(self) -> List[str]:
        """Get list of active symbols (from holdings)"""
        query = """
            SELECT DISTINCT stock_symbol
            FROM holdings
            WHERE stock_symbol IS NOT NULL AND stock_symbol != ''
            ORDER BY stock_symbol
        """
        holdings = db.execute_query(query)
        return [h['stock_symbol'] for h in holdings]


def main():
    """Main entry point for periodic worker"""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    logger.info("🚀 Starting Periodic Worker...")
    
    # Initialize database
    init_database()
    
    # Create and start worker
    worker = PeriodicWorker()
    
    try:
        worker.start()
        # Keep running
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down periodic worker...")
        worker.stop()


if __name__ == "__main__":
    main()

