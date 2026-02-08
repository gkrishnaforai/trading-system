"""
Universal Alert System Scheduler
Industry-standard job scheduling for universal alert system
Integrates with existing scheduler framework
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import json

from app.observability.logging import get_logger, log_operation_start, log_operation_success, log_operation_failure
from app.observability.metrics import get_metrics
from app.observability.audit import log_event
from app.services.universal_alert_service_enhanced import universal_alert_service
from app.services.notification_service import notification_service
from app.services.universal_plugins import plugin_registry

logger = get_logger("universal_scheduler")
metrics = get_metrics()

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class JobResult:
    """Result of a job execution"""
    job_name: str
    status: JobStatus
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: int
    records_processed: int = 0
    records_failed: int = 0
    alerts_generated: int = 0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None

class UniversalScheduler:
    """Scheduler for universal alert system jobs"""
    
    def __init__(self):
        self.job_configs = self._get_default_job_configs()
        self.is_running = False
        self.started_at: Optional[datetime] = None
        self.last_event_processing_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.last_job_run: Dict[str, Dict[str, Any]] = {}
    
    def _get_default_job_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get default job configurations"""
        return {
            'earnings_data_collection': {
                'interval_minutes': 60,
                'sources': ['fmp'],
                'fmp_api_key': None,  # Would get from environment
                'batch_size': 100,
                'enabled': True
            },
            'analyst_grades_collection': {
                'interval_minutes': 15,
                'sources': ['fmp'],
                'fmp_api_key': None,
                'batch_size': 50,
                'enabled': True
            },
            'price_movements_collection': {
                'interval_minutes': 5,
                'symbols': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],  # Would get from watchlists
                'threshold_percent': 5.0,
                'enabled': True
            },
            'event_processing': {
                'interval_minutes': 2,
                'batch_size': 100,
                'parallel_workers': 4,
                'enabled': True
            },
            'notification_delivery': {
                'interval_minutes': 1,
                'batch_size': 50,
                'retry_delay_minutes': 5,
                'enabled': True
            },
            'system_health_check': {
                'interval_minutes': 10,
                'enabled': True
            }
        }
    
    async def start_scheduler(self):
        """Start the universal alert scheduler"""
        if self.is_running:
            logger.warning("⚠️ Universal scheduler is already running")
            return
        
        self.is_running = True
        self.started_at = datetime.now()
        self.last_error = None
        logger.info("🚀 Starting Universal Alert Scheduler")
        
        # Start all job loops
        for job_name, config in self.job_configs.items():
            if config.get('enabled', True):
                asyncio.create_task(self._job_loop(job_name, config))
        
        logger.info(f"✅ Started {len(self.job_configs)} job loops")
    
    async def stop_scheduler(self):
        """Stop the universal alert scheduler"""
        self.is_running = False
        logger.info("🛑 Stopping Universal Alert Scheduler")
    
    async def _job_loop(self, job_name: str, config: Dict[str, Any]):
        """Main job loop for a specific job"""
        interval_minutes = config.get('interval_minutes', 5)
        
        while self.is_running:
            try:
                # Execute job
                result = await self._execute_job(job_name, config)

                self.last_job_run[job_name] = {
                    'status': result.status.value,
                    'started_at': result.started_at.isoformat() if result.started_at else None,
                    'completed_at': result.completed_at.isoformat() if result.completed_at else None,
                    'duration_ms': result.duration_ms,
                    'records_processed': result.records_processed,
                    'records_failed': result.records_failed,
                    'alerts_generated': result.alerts_generated,
                    'error_message': result.error_message,
                }

                if job_name == 'event_processing':
                    self.last_event_processing_at = datetime.now()
                
                # Log job completion
                await self._log_job_completion(job_name, result)
                
                # Wait for next interval
                await asyncio.sleep(interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"❌ Error in job loop {job_name}: {e}")
                self.last_error = str(e)
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _execute_job(self, job_name: str, config: Dict[str, Any]) -> JobResult:
        """Execute a specific job"""
        tracking_id = log_operation_start(
            logger, f"job_{job_name}",
            {'job_name': job_name, 'config': config}
        )
        
        start_time = datetime.now()
        
        try:
            # Log job start to audit trail
            log_event(
                level='info',
                operation=f"job_{job_name}",
                provider='universal_scheduler',
                message='job_start',
                context={'tracking_id': tracking_id, 'job_config': config},
            )
            
            # Execute job based on type
            if job_name == 'earnings_data_collection':
                result = await self._execute_earnings_collection(config)
            elif job_name == 'analyst_grades_collection':
                result = await self._execute_analyst_grades_collection(config)
            elif job_name == 'price_movements_collection':
                result = await self._execute_price_movements_collection(config)
            elif job_name == 'event_processing':
                result = await self._execute_event_processing(config)
            elif job_name == 'notification_delivery':
                result = await self._execute_notification_delivery(config)
            elif job_name == 'system_health_check':
                result = await self._execute_system_health_check(config)
            else:
                raise ValueError(f"Unknown job: {job_name}")
            
            # Calculate duration
            completed_time = datetime.now()
            duration_ms = int((completed_time - start_time).total_seconds() * 1000)
            
            result.started_at = start_time
            result.completed_at = completed_time
            result.duration_ms = duration_ms
            
            log_operation_success(
                logger, f"job_{job_name}", tracking_id,
                {
                    'records_processed': result.records_processed,
                    'records_failed': result.records_failed,
                    'alerts_generated': result.alerts_generated,
                    'duration_ms': duration_ms
                }
            )
            
            log_event(
                level='info',
                operation=f"job_{job_name}",
                provider='universal_scheduler',
                message='job_completed',
                duration_ms=duration_ms,
                context={
                    'tracking_id': tracking_id,
                    'records_processed': result.records_processed,
                    'records_failed': result.records_failed,
                    'alerts_generated': result.alerts_generated,
                },
            )
            
            metrics.increment(f'job_{job_name}_completed_total')
            metrics.record_duration(f'job_{job_name}_duration_seconds', duration_ms / 1000)
            
            return result
            
        except Exception as e:
            completed_time = datetime.now()
            duration_ms = int((completed_time - start_time).total_seconds() * 1000)
            
            result = JobResult(
                job_name=job_name,
                status=JobStatus.FAILED,
                started_at=start_time,
                completed_at=completed_time,
                duration_ms=duration_ms,
                error_message=str(e)
            )
            
            log_operation_failure(logger, f"job_{job_name}", tracking_id, e)
            
            log_event(
                level='error',
                operation=f"job_{job_name}",
                provider='universal_scheduler',
                message='job_failed',
                duration_ms=duration_ms,
                exception=e,
                context={'tracking_id': tracking_id, 'error': str(e)},
            )
            
            metrics.increment(f'job_{job_name}_failed_total')
            
            return result
    
    async def _execute_earnings_collection(self, config: Dict[str, Any]) -> JobResult:
        """Execute earnings data collection job"""
        try:
            plugin_config = {
                'sources': config.get('sources', ['fmp']),
                'fmp_api_key': config.get('fmp_api_key')
            }
            
            # Collect data using earnings plugin
            results = await universal_alert_service.collect_data_from_plugins({
                'earnings_calendar': plugin_config
            })
            
            events_collected = sum(len(events) for events in results.values())
            
            return JobResult(
                job_name='earnings_data_collection',
                status=JobStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=0,
                records_processed=events_collected,
                metadata={'plugin_results': results}
            )
            
        except Exception as e:
            logger.error(f"❌ Error in earnings collection job: {e}")
            raise
    
    async def _execute_analyst_grades_collection(self, config: Dict[str, Any]) -> JobResult:
        """Execute analyst grades collection job"""
        try:
            plugin_config = {
                'sources': config.get('sources', ['fmp']),
                'fmp_api_key': config.get('fmp_api_key')
            }
            
            # Collect data using analyst grades plugin
            results = await universal_alert_service.collect_data_from_plugins({
                'analyst_grades': plugin_config
            })
            
            events_collected = sum(len(events) for events in results.values())
            
            return JobResult(
                job_name='analyst_grades_collection',
                status=JobStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=0,
                records_processed=events_collected,
                metadata={'plugin_results': results}
            )
            
        except Exception as e:
            logger.error(f"❌ Error in analyst grades collection job: {e}")
            raise
    
    async def _execute_price_movements_collection(self, config: Dict[str, Any]) -> JobResult:
        """Execute price movements collection job"""
        try:
            plugin_config = {
                'symbols': config.get('symbols', []),
                'threshold_percent': config.get('threshold_percent', 5.0)
            }
            
            # Collect data using price movements plugin
            results = await universal_alert_service.collect_data_from_plugins({
                'price_movements': plugin_config
            })
            
            events_collected = sum(len(events) for events in results.values())
            
            return JobResult(
                job_name='price_movements_collection',
                status=JobStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=0,
                records_processed=events_collected,
                metadata={'plugin_results': results}
            )
            
        except Exception as e:
            logger.error(f"❌ Error in price movements collection job: {e}")
            raise
    
    async def _execute_event_processing(self, config: Dict[str, Any]) -> JobResult:
        """Execute event processing job"""
        try:
            batch_size = config.get('batch_size', 100)
            parallel_workers = config.get('parallel_workers', 4)
            
            # Get pending events
            pending_events = await universal_alert_service.event_repo.get_pending_events(limit=batch_size)
            
            processed_count = 0
            failed_count = 0
            alerts_generated = 0
            
            # Process events in parallel
            tasks = []
            for event_data in pending_events:
                # Create UniversalEvent from data
                from app.services.universal_alert_service_enhanced import UniversalEvent, EntityType
                
                event = UniversalEvent(
                    event_id=event_data['event_id'],
                    event_type=event_data['event_type'],
                    entity_type=EntityType(event_data['entity_type']),
                    entity_id=event_data['entity_id'],
                    event_data=event_data['event_data'],
                    event_timestamp=event_data['event_timestamp'],
                    data_source=event_data['data_source'],
                    confidence_score=event_data.get('confidence_score', 1.0)
                )
                
                tasks.append(universal_alert_service.process_event(event))
            
            # Wait for all tasks to complete
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        failed_count += 1
                        logger.error(f"❌ Error processing event: {result}")
                    else:
                        processed_count += 1
                        if result.get('success'):
                            alerts_generated += result.get('alerts_triggered', 0)
                        else:
                            failed_count += 1
            
            return JobResult(
                job_name='event_processing',
                status=JobStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=0,
                records_processed=processed_count,
                records_failed=failed_count,
                alerts_generated=alerts_generated
            )
            
        except Exception as e:
            logger.error(f"❌ Error in event processing job: {e}")
            raise
    
    async def _execute_notification_delivery(self, config: Dict[str, Any]) -> JobResult:
        """Execute notification delivery job"""
        try:
            batch_size = config.get('batch_size', 50)

            result = await notification_service.process_notifications(
                {'batch_size': batch_size, 'retry_delay_minutes': config.get('retry_delay_minutes', 5)},
                execution_context=None,
            )

            return JobResult(
                job_name='notification_delivery',
                status=JobStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=0,
                records_processed=result.get('records_processed', 0),
                records_failed=result.get('records_failed', 0),
                metadata=result,
            )
            
        except Exception as e:
            logger.error(f"❌ Error in notification delivery job: {e}")
            raise
    
    async def _execute_system_health_check(self, config: Dict[str, Any]) -> JobResult:
        """Execute system health check job"""
        try:
            # Get system health
            health = await universal_alert_service.get_system_health()
            
            # Get metrics
            current_metrics = metrics.get_metrics()
            
            # Log health status
            if health.get('status') == 'healthy':
                logger.info(f"✅ System health check passed: {health.get('pending_events', 0)} pending events")
            else:
                logger.warning(f"⚠️ System health check failed: {health.get('status')}")
            
            return JobResult(
                job_name='system_health_check',
                status=JobStatus.COMPLETED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
                duration_ms=0,
                metadata={
                    'health_status': health.get('status'),
                    'pending_events': health.get('pending_events', 0),
                    'plugin_count': len(health.get('plugins', {}).get('data_sources', []))
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Error in system health check job: {e}")
            raise
    
    async def _log_job_completion(self, job_name: str, result: JobResult):
        """Log job completion to database"""
        try:
            # This would integrate with your job execution log table
            # For now, just log to application log
            
            status = "✅" if result.status == JobStatus.COMPLETED else "❌"
            
            logger.info(f"{status} Job {job_name} completed in {result.duration_ms}ms")
            logger.info(f"   Processed: {result.records_processed}, Failed: {result.records_failed}, Alerts: {result.alerts_generated}")
            
            if result.error_message:
                logger.error(f"   Error: {result.error_message}")
            
        except Exception as e:
            logger.error(f"❌ Error logging job completion: {e}")
    
    def get_job_status(self) -> Dict[str, Any]:
        """Get current job status"""
        return {
            'scheduler_running': self.is_running,
            'configured_jobs': list(self.job_configs.keys()),
            'enabled_jobs': [name for name, config in self.job_configs.items() if config.get('enabled', True)],
            'job_configs': self.job_configs
        }
    
    def update_job_config(self, job_name: str, config: Dict[str, Any]):
        """Update job configuration"""
        if job_name in self.job_configs:
            self.job_configs[job_name].update(config)
            logger.info(f"✅ Updated job configuration: {job_name}")
        else:
            logger.error(f"❌ Job not found: {job_name}")

# Global scheduler instance
universal_scheduler = UniversalScheduler()
