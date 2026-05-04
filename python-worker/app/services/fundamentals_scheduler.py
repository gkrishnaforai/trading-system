"""
Fundamentals Data Scheduler Service
Automated daily fundamentals data collection at 10 AM and 6 PM EST
"""

import asyncio
import logging
from datetime import datetime, time
from typing import List, Dict, Any
from sqlalchemy import text
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from app.database import get_db
from app.ingestion.profiles import get_profile
from app.observability.logging import get_logger
from app.utils.notifications import send_alert_notification

logger = get_logger("fundamentals_scheduler")

class FundamentalsScheduler:
    """Daily fundamentals data collection scheduler"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.timezone = pytz.timezone('America/New_York')  # EST timezone
        self.running = False
        
        # Data types to collect (focusing on the ones that were missing)
        self.target_data_types = [
            'stock_grades',
            'analyst_ratings', 
            'price_targets',
            'consensus_data'
        ]
    
    async def start(self):
        """Start the fundamentals scheduler"""
        if not self.running:
            self.scheduler.start()
            self.running = True
            logger.info("🚀 Fundamentals scheduler started")
            
            # Schedule daily runs at 10 AM and 6 PM EST
            await self.schedule_daily_runs()
    
    async def stop(self):
        """Stop the scheduler"""
        if self.running:
            self.scheduler.shutdown(wait=True)
            self.running = False
            logger.info("⏹️ Fundamentals scheduler stopped")
    
    async def schedule_daily_runs(self):
        """Schedule daily fundamentals data collection"""
        try:
            # Morning run - 10:00 AM EST
            morning_trigger = CronTrigger(
                hour=10,
                minute=0,
                timezone=self.timezone
            )
            
            self.scheduler.add_job(
                func=self.run_fundamentals_collection,
                trigger=morning_trigger,
                args=["morning"],
                id="fundamentals_morning",
                name="Daily Fundamentals Collection - Morning (10 AM EST)",
                replace_existing=True
            )
            
            # Evening run - 6:00 PM EST  
            evening_trigger = CronTrigger(
                hour=18,
                minute=0,
                timezone=self.timezone
            )
            
            self.scheduler.add_job(
                func=self.run_fundamentals_collection,
                trigger=evening_trigger,
                args=["evening"],
                id="fundamentals_evening",
                name="Daily Fundamentals Collection - Evening (6 PM EST)",
                replace_existing=True
            )
            
            logger.info("📅 Scheduled daily fundamentals collection:")
            logger.info("   - Morning: 10:00 AM EST")
            logger.info("   - Evening: 6:00 PM EST")
            
        except Exception as e:
            logger.error(f"❌ Error scheduling daily runs: {e}")
    
    async def run_fundamentals_collection(self, run_time: str):
        """Run the comprehensive fundamentals data collection"""
        logger.info(f"🔄 Starting {run_time} fundamentals data collection")
        
        try:
            # Get all active symbols from database
            symbols = await self.get_active_symbols()
            
            if not symbols:
                logger.warning("⚠️ No active symbols found for fundamentals collection")
                return
            
            logger.info(f"📊 Collecting fundamentals for {len(symbols)} symbols")
            
            # Get the comprehensive weekly fundamentals enhanced profile
            profile = get_profile('weekly_fundamentals_enhanced')
            
            results = {
                'successful': [],
                'failed': [],
                'alerts_generated': []
            }
            
            # Process each symbol
            for symbol in symbols:
                try:
                    logger.info(f"📈 Processing {symbol}...")
                    
                    # Run the comprehensive profile
                    result = profile.execute(f'fundamentals-{run_time}-{datetime.now().strftime("%Y%m%d")}', [symbol])
                    
                    # Check results and generate alerts for missing data
                    symbol_result = await self.process_symbol_result(symbol, result, run_time)
                    
                    if symbol_result['status'] == 'success':
                        results['successful'].append(symbol_result)
                    else:
                        results['failed'].append(symbol_result)
                    
                    # Generate alerts if needed
                    if symbol_result.get('alerts'):
                        results['alerts_generated'].extend(symbol_result['alerts'])
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {symbol}: {e}")
                    results['failed'].append({
                        'symbol': symbol,
                        'error': str(e),
                        'status': 'failed'
                    })
            
            # Log summary
            await self.log_collection_summary(results, run_time)
            
        except Exception as e:
            logger.error(f"❌ Error in {run_time} fundamentals collection: {e}")
    
    async def get_active_symbols(self) -> List[str]:
        """Get list of active symbols from database"""
        try:
            db = get_db()
            query = """
            SELECT DISTINCT symbol 
            FROM symbols 
            WHERE is_active = true 
            ORDER BY symbol
            """
            result = await db.execute(query)
            symbols = [row[0] for row in result.fetchall()]
            return symbols
            
        except Exception as e:
            logger.error(f"❌ Error getting active symbols: {e}")
            return []
    
    async def process_symbol_result(self, symbol: str, result: Dict[str, Any], run_time: str) -> Dict[str, Any]:
        """Process results for a single symbol and generate alerts"""
        symbol_result = {
            'symbol': symbol,
            'status': 'success',
            'data_types_collected': [],
            'data_types_missing': [],
            'alerts': []
        }
        
        try:
            # Check what data was successfully collected
            if 'results' in result:
                for res in result['results']:
                    if res.get('symbol') == symbol:
                        if 'details' in res and 'results' in res['details']:
                            for dt, dt_result in res['details']['results'].items():
                                status = dt_result.get('status', 'unknown')
                                rows = dt_result.get('rows_affected', 0)
                                
                                if status == 'success' and rows > 0:
                                    symbol_result['data_types_collected'].append(dt)
                                elif status == 'skipped' or rows == 0:
                                    symbol_result['data_types_missing'].append(dt)
            
            # Generate alerts for missing critical data
            missing_critical = []
            for data_type in self.target_data_types:
                if data_type in symbol_result['data_types_missing']:
                    missing_critical.append(data_type)
            
            if missing_critical:
                alert = await self.generate_missing_data_alert(symbol, missing_critical, run_time)
                symbol_result['alerts'].append(alert)
            
            logger.info(f"✅ {symbol}: {len(symbol_result['data_types_collected'])} collected, {len(missing_critical)} missing")
            
        except Exception as e:
            logger.error(f"❌ Error processing {symbol} result: {e}")
            symbol_result['status'] = 'failed'
            symbol_result['error'] = str(e)
        
        return symbol_result
    
    async def generate_missing_data_alert(self, symbol: str, missing_data: List[str], run_time: str) -> Dict[str, Any]:
        """Generate alert for missing critical data"""
        alert = {
            'symbol': symbol,
            'alert_type': 'missing_fundamentals_data',
            'severity': 'medium',
            'title': f'Missing Fundamentals Data for {symbol}',
            'message': f"The following critical data types are not available: {', '.join(missing_data)}",
            'missing_data': missing_data,
            'run_time': run_time,
            'timestamp': datetime.now(),
            'action_required': 'review_data_sources'
        }
        
        try:
            # Send alert notification (if notification system is configured)
            await send_alert_notification(alert)
            logger.info(f"🚨 Generated alert for {symbol}: missing {', '.join(missing_data)}")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not send alert notification: {e}")
        
        return alert
    
    async def log_collection_summary(self, results: Dict[str, Any], run_time: str):
        """Log summary of collection results"""
        successful = len(results['successful'])
        failed = len(results['failed'])
        alerts = len(results['alerts_generated'])
        
        logger.info(f"📊 {run_time.title()} Fundamentals Collection Summary:")
        logger.info(f"   ✅ Successful: {successful}")
        logger.info(f"   ❌ Failed: {failed}")
        logger.info(f"   🚨 Alerts Generated: {alerts}")
        
        if alerts > 0:
            logger.info("🔔 Missing data alerts sent for review")
    
    def get_schedule_status(self) -> Dict[str, Any]:
        """Get current scheduler status"""
        jobs = []
        if self.running:
            for job in self.scheduler.get_jobs():
                jobs.append({
                    'id': job.id,
                    'name': job.name,
                    'next_run': job.next_run_time,
                    'trigger': str(job.trigger)
                })
        
        return {
            'running': self.running,
            'timezone': str(self.timezone),
            'jobs': jobs,
            'total_jobs': len(jobs)
        }

# Global scheduler instance
fundamentals_scheduler = FundamentalsScheduler()

async def start_fundamentals_scheduler():
    """Start the fundamentals scheduler"""
    await fundamentals_scheduler.start()

async def stop_fundamentals_scheduler():
    """Stop the fundamentals scheduler"""
    await fundamentals_scheduler.stop()

def get_fundamentals_scheduler_status() -> Dict[str, Any]:
    """Get fundamentals scheduler status"""
    return fundamentals_scheduler.get_schedule_status()
