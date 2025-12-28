"""
Nightly batch worker for data fetching and indicator calculations
Industry Standard: EOD workflow with proper separation of daily vs periodic updates

SOLID: Single Responsibility - orchestrates batch jobs
DRY: Reuses EODWorkflow and UpdateStrategy
"""
import logging
from datetime import datetime
from typing import List
import schedule
import time

from app.config import settings
from app.database import init_database
from app.workflows.eod_workflow import EODWorkflow
from app.workflows.update_strategy import UpdateStrategy
from app.services.market_movers_service import MarketMoversService
from app.services.sector_performance_service import SectorPerformanceService
from app.services.market_overview_service import MarketOverviewService
from app.services.market_trends_service import MarketTrendsService
from app.observability.metrics import get_metrics, track_duration

logger = logging.getLogger(__name__)
metrics = get_metrics()


class BatchWorker:
    """
    Batch worker for scheduled data updates
    
    Industry Standard EOD Workflow:
    1. Market Close
    2. Load Daily Price + Volume (raw OHLCV)
    3. Validate & Adjust
    4. Recompute Indicators (from fresh price data)
    5. Generate Signals
    6. Update Watchlists & Portfolios
    7. Trigger Alerts
    8. Generate Reports (optional)
    
    SOLID: Single Responsibility - orchestrates batch jobs only
    DRY: Reuses EODWorkflow, avoids duplication
    """
    
    def __init__(self):
        self.eod_workflow = EODWorkflow()
        self.update_strategy = UpdateStrategy()
        self.market_movers_service = MarketMoversService()
        self.sector_performance_service = SectorPerformanceService()
        self.market_overview_service = MarketOverviewService()
        self.market_trends_service = MarketTrendsService()
        self.running = False
    
    @track_duration('batch_job_duration_seconds')
    def run_nightly_batch(self):
        """
        Execute nightly EOD batch job
        
        Industry Standard Workflow:
        1. Load Daily Price + Volume (raw OHLCV)
        2. Validate & Adjust
        3. Recompute Indicators (from fresh price data)
        4. Generate Signals
        5. Update Watchlists & Portfolios
        6. Trigger Alerts
        7. Market aggregations (movers, sectors, trends)
        """
        metrics.increment('batch_job_runs_total')
        logger.info("🌙 Starting EOD batch job...")
        start_time = datetime.now()
        
        try:
            # Get symbols needing daily update
            symbols = self.update_strategy.get_symbols_needing_daily_update()
            logger.info(f"📊 Found {len(symbols)} symbols needing daily EOD update")
            
            # Execute EOD workflow (stages 1-6)
            eod_result = self.eod_workflow.execute_daily_eod_workflow(symbols)
            
            if not eod_result.get('success'):
                logger.error(f"❌ EOD workflow failed: {eod_result.get('error')}")
                metrics.increment('batch_job_failures_total')
                return
            
            # Stage 7: Market aggregations (movers, sectors, trends, overview)
            logger.info("📈 Calculating market aggregations...")
            self._calculate_market_aggregations()
            
            elapsed = (datetime.now() - start_time).total_seconds()
            metrics.increment('batch_job_success_total')
            metrics.set_gauge('batch_job_last_success_timestamp', start_time.timestamp())
            
            logger.info(f"✅ EOD batch job completed in {elapsed:.2f} seconds")
            logger.info(f"   - Price loading: {eod_result['stages']['price_loading']['succeeded']} succeeded, {eod_result['stages']['price_loading']['failed']} failed")
            logger.info(f"   - Indicators: {eod_result['stages']['indicator_recomputation']['succeeded']} succeeded, {eod_result['stages']['indicator_recomputation']['failed']} failed")
            logger.info(f"   - Signals: {eod_result['stages']['signal_generation']['succeeded']} succeeded, {eod_result['stages']['signal_generation']['failed']} failed")
            
        except Exception as e:
            metrics.increment('batch_job_failures_total')
            logger.error(f"❌ Error in EOD batch job: {e}", exc_info=True)
            raise
    
    def _calculate_market_aggregations(self):
        """Calculate market-level aggregations (movers, sectors, trends, overview)"""
        try:
            movers = self.market_movers_service.calculate_market_movers(period="day", limit=20)
            logger.info(f"✅ Market movers: {len(movers.get('gainers', []))} gainers, {len(movers.get('losers', []))} losers")
        except Exception as e:
            logger.error(f"Error calculating market movers: {e}")
        
        try:
            sector_perf = self.sector_performance_service.calculate_sector_performance()
            logger.info(f"✅ Sector performance: {len(sector_perf.get('sectors', []))} sectors")
        except Exception as e:
            logger.error(f"Error calculating sector performance: {e}")
        
        try:
            overview = self.market_overview_service.get_market_overview()
            logger.info(f"✅ Market overview: {overview.get('market_status', 'N/A')}")
        except Exception as e:
            logger.error(f"Error calculating market overview: {e}")
        
        try:
            trends = self.market_trends_service.calculate_market_trends()
            logger.info(f"✅ Market trends: {trends.get('overall', {}).get('direction', 'N/A')}")
        except Exception as e:
            logger.error(f"Error calculating market trends: {e}")
    
    
    def start_scheduler(self):
        """Start the scheduled batch job"""
        # Schedule nightly batch at configured time
        schedule.every().day.at(
            f"{settings.batch_schedule_hour:02d}:{settings.batch_schedule_minute:02d}"
        ).do(self.run_nightly_batch)
        
        logger.info(
            f"📅 Batch scheduler started. Nightly job scheduled for "
            f"{settings.batch_schedule_hour:02d}:{settings.batch_schedule_minute:02d}"
        )
        
        self.running = True
        
        # Run scheduler loop
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Batch scheduler stopped")


def main():
    """Main entry point for batch worker"""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    logger.info("🚀 Starting Batch Worker...")
    
    # Initialize database
    init_database()
    
    # Create and start worker
    worker = BatchWorker()
    
    # Run initial batch (optional, for testing)
    # worker.run_nightly_batch()
    
    # Start scheduler
    try:
        worker.start_scheduler()
    except KeyboardInterrupt:
        logger.info("Shutting down batch worker...")
        worker.stop()


if __name__ == "__main__":
    main()

