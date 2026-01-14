"""
Portfolio Analysis Scheduling Service
Automated portfolio analysis with configurable schedules and notifications
"""

import asyncio
import logging
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

from app.database import get_db
from app.api.portfolio_api import analyze_portfolio as run_portfolio_analysis
from app.utils.notifications import send_email_notification, send_push_notification

logger = logging.getLogger(__name__)

class PortfolioScheduler:
    """Portfolio analysis scheduling service"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.timezone = pytz.timezone('America/New_York')  # Default to EST
        self.running = False
    
    async def start(self):
        """Start the scheduler"""
        if not self.running:
            self.scheduler.start()
            self.running = True
            logger.info("Portfolio scheduler started")
            
            # Load existing schedules from database
            await self.load_schedules_from_db()
    
    async def stop(self):
        """Stop the scheduler"""
        if self.running:
            self.scheduler.shutdown(wait=True)
            self.running = False
            logger.info("Portfolio scheduler stopped")
    
    async def load_schedules_from_db(self):
        """Load all active schedules from database"""
        try:
            db = get_db()
            
            # Get all active scheduled analyses
            schedules = db.execute(
                """
                SELECT sa.id, sa.user_id, sa.portfolio_id, sa.schedule_type,
                       sa.schedule_time, sa.schedule_day, sa.notification_preferences,
                       u.email, u.username, p.name as portfolio_name
                FROM scheduled_analyses sa
                JOIN users u ON sa.user_id = u.id
                JOIN portfolios p ON sa.portfolio_id = p.id
                WHERE sa.is_active = true
                """
            ).fetchall()
            
            for schedule in schedules:
                await self.add_schedule_from_db(schedule)
            
            logger.info(f"Loaded {len(schedules)} schedules from database")
            
        except Exception as e:
            logger.error(f"Error loading schedules from database: {str(e)}")
    
    async def add_schedule_from_db(self, schedule: tuple):
        """Add a schedule from database record"""
        (schedule_id, user_id, portfolio_id, schedule_type, 
         schedule_time, schedule_day, notification_preferences,
         user_email, username, portfolio_name) = schedule
        
        try:
            # Parse schedule time
            if isinstance(schedule_time, str):
                schedule_time = datetime.strptime(schedule_time, '%H:%M:%S').time()
            
            # Create job ID
            job_id = f"portfolio_{portfolio_id}_{schedule_id}"
            
            # Remove existing job if exists
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            # Create trigger based on schedule type
            if schedule_type == "daily":
                trigger = CronTrigger(
                    hour=schedule_time.hour,
                    minute=schedule_time.minute,
                    timezone=self.timezone
                )
            elif schedule_type == "weekly":
                if schedule_day:
                    # Convert to cron day format (0=Sunday, 6=Saturday)
                    cron_day = schedule_day - 1 if schedule_day > 1 else 6
                    trigger = CronTrigger(
                        day_of_week=cron_day,
                        hour=schedule_time.hour,
                        minute=schedule_time.minute,
                        timezone=self.timezone
                    )
                else:
                    # Default to Monday
                    trigger = CronTrigger(
                        day_of_week=0,
                        hour=schedule_time.hour,
                        minute=schedule_time.minute,
                        timezone=self.timezone
                    )
            elif schedule_type == "monthly":
                if schedule_day:
                    trigger = CronTrigger(
                        day=schedule_day,
                        hour=schedule_time.hour,
                        minute=schedule_time.minute,
                        timezone=self.timezone
                    )
                else:
                    # Default to 1st of month
                    trigger = CronTrigger(
                        day=1,
                        hour=schedule_time.hour,
                        minute=schedule_time.minute,
                        timezone=self.timezone
                    )
            else:
                logger.error(f"Unknown schedule type: {schedule_type}")
                return
            
            # Add job to scheduler
            self.scheduler.add_job(
                func=self.run_scheduled_analysis,
                trigger=trigger,
                args=[schedule_id, user_id, portfolio_id, notification_preferences,
                      user_email, username, portfolio_name],
                id=job_id,
                name=f"Portfolio Analysis - {portfolio_name}",
                replace_existing=True
            )
            
            logger.info(f"Added schedule: {job_id} - {portfolio_name} ({schedule_type})")
            
        except Exception as e:
            logger.error(f"Error adding schedule {schedule_id}: {str(e)}")
    
    async def run_scheduled_analysis(self, schedule_id: int, user_id: int, portfolio_id: int,
                                   notification_preferences: Dict[str, bool],
                                   user_email: str, username: str, portfolio_name: str):
        """Run scheduled portfolio analysis"""
        logger.info(f"Running scheduled analysis for portfolio {portfolio_id} (schedule {schedule_id})")
        
        try:
            # Run portfolio analysis
            result = await self._run_portfolio_analysis_async(portfolio_id)
            
            if result and result.get('success'):
                # Update last run time
                await self._update_schedule_run_time(schedule_id)
                
                # Send notifications
                await self._send_analysis_notifications(
                    user_id, portfolio_id, result, notification_preferences,
                    user_email, username, portfolio_name
                )
                
                logger.info(f"Completed scheduled analysis for portfolio {portfolio_id}")
            else:
                logger.error(f"Scheduled analysis failed for portfolio {portfolio_id}: {result.get('error', 'Unknown error')}")
                
                # Send error notification
                await self._send_error_notification(
                    user_id, portfolio_id, result.get('error', 'Unknown error'),
                    notification_preferences, user_email, username, portfolio_name
                )
        
        except Exception as e:
            logger.error(f"Error running scheduled analysis for portfolio {portfolio_id}: {str(e)}")
            
            # Send error notification
            await self._send_error_notification(
                user_id, portfolio_id, str(e),
                notification_preferences, user_email, username, portfolio_name
            )
    
    async def _run_portfolio_analysis_async(self, portfolio_id: int) -> Optional[Dict[str, Any]]:
        """Run portfolio analysis asynchronously"""
        try:
            # This would typically call the same logic as the API endpoint
            # For now, we'll simulate the analysis
            from app.api.portfolio_api import analyze_portfolio
            
            # Create a mock user context (in real implementation, get from database)
            mock_user = {"id": 1, "username": "scheduler", "role": "admin"}
            
            # Run analysis
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: analyze_portfolio(portfolio_id)
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error in portfolio analysis: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _update_schedule_run_time(self, schedule_id: int):
        """Update the last run time for a schedule"""
        try:
            db = get_db()
            db.execute(
                "UPDATE scheduled_analyses SET last_run = %s WHERE id = %s",
                (datetime.now(), schedule_id)
            )
            db.commit()
        except Exception as e:
            logger.error(f"Error updating schedule run time: {str(e)}")
    
    async def _send_analysis_notifications(self, user_id: int, portfolio_id: int,
                                        result: Dict[str, Any], notification_preferences: Dict[str, bool],
                                        user_email: str, username: str, portfolio_name: str):
        """Send notifications for completed analysis"""
        try:
            # Prepare notification content
            subject = f"Portfolio Analysis Complete - {portfolio_name}"
            
            # Create HTML email content
            html_content = self._create_analysis_email_html(result, portfolio_name)
            
            # Create text content
            text_content = self._create_analysis_email_text(result, portfolio_name)
            
            # Send email notification
            if notification_preferences.get('email', False):
                await self._send_email_async(user_email, subject, html_content, text_content)
            
            # Send push notification
            if notification_preferences.get('push', False):
                await self._send_push_async(user_id, {
                    "title": "Portfolio Analysis Complete",
                    "body": f"{result['signals_generated']} signals generated for {portfolio_name}",
                    "data": {
                        "portfolio_id": portfolio_id,
                        "analysis_result": result
                    }
                })
        
        except Exception as e:
            logger.error(f"Error sending analysis notifications: {str(e)}")
    
    async def _send_error_notification(self, user_id: int, portfolio_id: int, error_message: str,
                                     notification_preferences: Dict[str, bool],
                                     user_email: str, username: str, portfolio_name: str):
        """Send error notification"""
        try:
            subject = f"Portfolio Analysis Failed - {portfolio_name}"
            
            html_content = f"""
            <html>
            <body>
                <h2>❌ Portfolio Analysis Failed</h2>
                <p><strong>Portfolio:</strong> {portfolio_name}</p>
                <p><strong>Error:</strong> {error_message}</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Please check your portfolio and try again.</p>
            </body>
            </html>
            """
            
            text_content = f"""
            Portfolio Analysis Failed
            
            Portfolio: {portfolio_name}
            Error: {error_message}
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            Please check your portfolio and try again.
            """
            
            if notification_preferences.get('email', False):
                await self._send_email_async(user_email, subject, html_content, text_content)
            
            if notification_preferences.get('push', False):
                await self._send_push_async(user_id, {
                    "title": "Portfolio Analysis Failed",
                    "body": f"Analysis failed for {portfolio_name}: {error_message}",
                    "data": {"portfolio_id": portfolio_id, "error": error_message}
                })
        
        except Exception as e:
            logger.error(f"Error sending error notifications: {str(e)}")
    
    def _create_analysis_email_html(self, result: Dict[str, Any], portfolio_name: str) -> str:
        """Create HTML email content for analysis results"""
        return f"""
        <html>
        <body>
            <h2>📊 Portfolio Analysis Complete</h2>
            <p><strong>Portfolio:</strong> {portfolio_name}</p>
            <p><strong>Analysis Date:</strong> {result.get('analysis_date', 'N/A')}</p>
            
            <h3>📈 Summary</h3>
            <ul>
                <li>Symbols Analyzed: {result.get('symbols_analyzed', 0)}</li>
                <li>Signals Generated: {result.get('signals_generated', 0)}</li>
                <li>Success Rate: {result.get('success_rate', 0):.1f}%</li>
            </ul>
            
            {self._create_signals_table_html(result.get('results', []))}
            
            <p><em>This is an automated message from your Portfolio Analysis System.</em></p>
        </body>
        </html>
        """
    
    def _create_analysis_email_text(self, result: Dict[str, Any], portfolio_name: str) -> str:
        """Create text email content for analysis results"""
        content = f"""
Portfolio Analysis Complete

Portfolio: {portfolio_name}
Analysis Date: {result.get('analysis_date', 'N/A')}

Summary:
- Symbols Analyzed: {result.get('symbols_analyzed', 0)}
- Signals Generated: {result.get('signals_generated', 0)}
- Success Rate: {result.get('success_rate', 0):.1f}%
"""
        
        if result.get('results'):
            content += "\nSignals:\n"
            for signal_result in result['results'][:10]:  # Limit to first 10
                content += f"- {signal_result['symbol']}: {signal_result['signal']} ({signal_result['confidence']:.1f}%)\n"
        
        content += "\nThis is an automated message from your Portfolio Analysis System."
        return content
    
    def _create_signals_table_html(self, signals: List[Dict[str, Any]]) -> str:
        """Create HTML table for signals"""
        if not signals:
            return ""
        
        table_html = """
        <h3>🎯 Generated Signals</h3>
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f2f2f2;">
                <th style="padding: 8px;">Symbol</th>
                <th style="padding: 8px;">Signal</th>
                <th style="padding: 8px;">Confidence</th>
                <th style="padding: 8px;">Price</th>
            </tr>
        """
        
        for signal in signals[:20]:  # Limit to first 20 signals
            signal_color = {
                'BUY': '#00C851',
                'SELL': '#FF4444',
                'HOLD': '#FF8800'
            }.get(signal['signal'], '#666666')
            
            table_html += f"""
            <tr>
                <td style="padding: 8px;"><strong>{signal['symbol']}</strong></td>
                <td style="padding: 8px; color: {signal_color}; font-weight: bold;">{signal['signal']}</td>
                <td style="padding: 8px;">{signal['confidence']:.1f}%</td>
                <td style="padding: 8px;">${signal['price']:.2f}</td>
            </tr>
            """
        
        table_html += "</table>"
        
        if len(signals) > 20:
            table_html += f"<p><em>Showing first 20 of {len(signals)} signals</em></p>"
        
        return table_html
    
    async def _send_email_async(self, email: str, subject: str, html_content: str, text_content: str):
        """Send email asynchronously"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, send_email_notification, email, subject, html_content, text_content
            )
        except Exception as e:
            logger.error(f"Error sending email to {email}: {str(e)}")
    
    async def _send_push_async(self, user_id: int, notification_data: Dict[str, Any]):
        """Send push notification asynchronously"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, send_push_notification, user_id, notification_data
            )
        except Exception as e:
            logger.error(f"Error sending push notification to user {user_id}: {str(e)}")
    
    def get_schedule_status(self) -> Dict[str, Any]:
        """Get scheduler status and job information"""
        jobs = []
        
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "running": self.running,
            "jobs": jobs,
            "job_count": len(jobs)
        }
    
    async def add_schedule(self, schedule_id: int, user_id: int, portfolio_id: int,
                         schedule_type: str, schedule_time: time, schedule_day: Optional[int] = None,
                         notification_preferences: Dict[str, Any] = None):
        """Add a new schedule"""
        try:
            db = get_db()
            
            # Get user and portfolio info
            schedule_info = db.execute(
                """
                SELECT u.email, u.username, p.name as portfolio_name
                FROM users u
                JOIN portfolios p ON p.id = %s
                WHERE u.id = %s
                """,
                (portfolio_id, user_id)
            ).fetchone()
            
            if schedule_info:
                user_email, username, portfolio_name = schedule_info
                
                # Add to scheduler
                await self.add_schedule_from_db((
                    schedule_id, user_id, portfolio_id, schedule_type,
                    schedule_time, schedule_day, notification_preferences or {},
                    user_email, username, portfolio_name
                ))
                
                return True
            else:
                logger.error(f"User or portfolio not found for schedule {schedule_id}")
                return False
        
        except Exception as e:
            logger.error(f"Error adding schedule {schedule_id}: {str(e)}")
            return False
    
    async def remove_schedule(self, schedule_id: int, portfolio_id: int):
        """Remove a schedule"""
        try:
            job_id = f"portfolio_{portfolio_id}_{schedule_id}"
            
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed schedule: {job_id}")
                return True
            else:
                logger.warning(f"Schedule not found: {job_id}")
                return False
        
        except Exception as e:
            logger.error(f"Error removing schedule {schedule_id}: {str(e)}")
            return False
    
    async def update_schedule(self, schedule_id: int, portfolio_id: int,
                            schedule_type: str, schedule_time: time, schedule_day: Optional[int] = None,
                            notification_preferences: Dict[str, Any] = None):
        """Update an existing schedule"""
        # Remove old schedule
        await self.remove_schedule(schedule_id, portfolio_id)
        
        # Add new schedule
        return await self.add_schedule(schedule_id, 0, portfolio_id, schedule_type, 
                                     schedule_time, schedule_day, notification_preferences)

# Global scheduler instance
portfolio_scheduler = PortfolioScheduler()

async def start_portfolio_scheduler():
    """Start the portfolio scheduler"""
    await portfolio_scheduler.start()

async def stop_portfolio_scheduler():
    """Stop the portfolio scheduler"""
    await portfolio_scheduler.stop()

def get_scheduler_status() -> Dict[str, Any]:
    """Get scheduler status"""
    return portfolio_scheduler.get_schedule_status()
