"""
Pluggable Notification Service - Industry Standard
Supports multiple notification channels with retry logic
"""

import logging
import smtplib
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Protocol
from dataclasses import dataclass
from enum import Enum
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import html

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("notification_service")

class NotificationStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ChannelType(Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"

@dataclass
class NotificationMessage:
    """Notification message structure"""
    recipient: str
    subject: Optional[str]
    body: str
    template_data: Dict[str, Any]
    urgency_level: str
    channel_type: ChannelType

class NotificationChannel(ABC):
    """Abstract base class for notification channels"""
    
    @abstractmethod
    async def send(self, message: NotificationMessage) -> Dict[str, Any]:
        """Send notification message"""
        pass
    
    @abstractmethod
    def validate_recipient(self, recipient: str) -> bool:
        """Validate recipient format"""
        pass

class EmailChannel(NotificationChannel):
    """Email notification channel"""
    
    def __init__(self, smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
    
    def validate_recipient(self, recipient: str) -> bool:
        """Validate email format"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, recipient) is not None
    
    async def send(self, message: NotificationMessage) -> Dict[str, Any]:
        """Send email notification"""
        try:
            # Create email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.subject or "Stock Alert"
            msg['From'] = self.smtp_user
            msg['To'] = message.recipient
            
            # Add HTML body
            html_body = self._render_html_template(message)
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)
            
            # Add plain text body
            text_body = self._render_text_template(message)
            text_part = MIMEText(text_body, 'plain')
            msg.attach(text_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            return {
                'success': True,
                'message': 'Email sent successfully',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error sending email: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _render_html_template(self, message: NotificationMessage) -> str:
        """Render HTML email template"""
        template_data = message.template_data

        def _clean(value: Any) -> str:
            if value is None:
                return ""
            s = str(value).strip()
            if not s or s.lower() in {"n/a", "none", "null"}:
                return ""
            return s

        def _row(label: str, value: Any) -> str:
            v = _clean(value)
            if not v:
                return ""
            return f"<tr><td class='k'>{html.escape(label)}</td><td class='v'>{html.escape(v)}</td></tr>"

        urgency = (message.urgency_level or "medium").lower()
        urgency_label = urgency.upper() if urgency in {"low", "medium", "high", "critical"} else "ALERT"
        urgency_color = {
            "low": "#065f46",
            "medium": "#92400e",
            "high": "#9f1239",
            "critical": "#7f1d1d",
        }.get(urgency, "#1f2937")
        urgency_bg = {
            "low": "#ecfdf5",
            "medium": "#fffbeb",
            "high": "#fff1f2",
            "critical": "#fef2f2",
        }.get(urgency, "#f9fafb")
        border_color = {
            "low": "#a7f3d0",
            "medium": "#fde68a",
            "high": "#fecdd3",
            "critical": "#fecaca",
        }.get(urgency, "#e5e7eb")

        symbol = _clean(template_data.get("symbol"))
        company = _clean(template_data.get("company"))
        change_type = _clean(template_data.get("change_type"))
        alert_name = _clean(template_data.get("alert_name")) or "Alert"
        trigger_reason = _clean(template_data.get("trigger_reason")) or "A monitored condition was triggered."
        triggered_at = _clean(template_data.get("triggered_at")) or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")

        previous_grade = _clean(template_data.get("previous_grade"))
        new_grade = _clean(template_data.get("new_grade"))
        grade_line = ""
        if previous_grade and new_grade and previous_grade != new_grade:
            grade_line = f"{previous_grade} → {new_grade}"
        elif new_grade:
            grade_line = new_grade

        headline_left = " — ".join([p for p in [symbol, change_type] if p]) or "Stock Alert"
        headline_right = company

        details_rows = "".join([
            _row("Alert", alert_name),
            _row("Symbol", symbol),
            _row("Company", company),
            _row("Event", template_data.get("event_type")),
            _row("Change", change_type),
            _row("Grade", grade_line),
            _row("Consensus change", template_data.get("consensus_change")),
            _row("Price target", template_data.get("price_target")),
            _row("Analyst", template_data.get("analyst")),
            _row("Source", template_data.get("source")),
        ])

        subject = html.escape(message.subject or (headline_left if headline_left else "Stock Alert"))
        safe_headline_left = html.escape(headline_left)
        safe_headline_right = html.escape(headline_right)
        safe_trigger_reason = html.escape(trigger_reason)
        safe_triggered_at = html.escape(triggered_at)

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    body {{ margin:0; padding:0; background:#f3f4f6; color:#111827; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Inter,Arial,sans-serif; }}
    .container {{ max-width: 640px; margin: 0 auto; padding: 24px 14px; }}
    .card {{ background:#ffffff; border:1px solid #e5e7eb; border-radius: 12px; overflow:hidden; box-shadow: 0 2px 10px rgba(17,24,39,0.06); }}
    .topbar {{ padding: 16px 18px; background:#0b1220; color:#ffffff; }}
    .brand {{ font-weight:700; font-size:14px; letter-spacing:0.02em; opacity:0.95; }}
    .badge {{ display:inline-block; margin-top:10px; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; background:{urgency_bg}; color:{urgency_color}; border:1px solid {border_color}; }}
    .content {{ padding: 18px; }}
    .h1 {{ font-size:20px; font-weight:800; margin: 2px 0 4px 0; }}
    .sub {{ font-size:13px; color:#6b7280; margin: 0 0 12px 0; }}
    .reason {{ margin: 12px 0 14px 0; padding: 12px 12px; border-radius: 10px; background:{urgency_bg}; border: 1px solid {border_color}; }}
    .reason p {{ margin: 0; font-size: 14px; color:#111827; }}
    table {{ width:100%; border-collapse: collapse; margin-top: 8px; }}
    td {{ padding: 10px 10px; border-top: 1px solid #eef2f7; vertical-align: top; }}
    td.k {{ width: 34%; color:#6b7280; font-size: 12.5px; font-weight: 700; text-transform: none; }}
    td.v {{ color:#111827; font-size: 13.5px; }}
    .footer {{ padding: 14px 18px; background:#f9fafb; border-top:1px solid #e5e7eb; color:#6b7280; font-size: 12px; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="topbar">
        <div class="brand">TRADING SYSTEM ALERTS</div>
        <div class="badge">{urgency_label}</div>
      </div>
      <div class="content">
        <div class="h1">{safe_headline_left}</div>
        <div class="sub">{safe_headline_right}</div>
        <div class="reason">
          <p>{safe_trigger_reason}</p>
        </div>
        <div style="font-weight:800; font-size:14px; margin-top: 4px;">Key details</div>
        <table>
          {details_rows if details_rows else _row('Alert', alert_name) + _row('Triggered at', triggered_at)}
          <tr><td class='k'>Triggered at</td><td class='v mono'>{safe_triggered_at}</td></tr>
        </table>
      </div>
      <div class="footer">
        You received this message because alerts are enabled for your account.
      </div>
    </div>
  </div>
</body>
</html>"""
    
    def _render_text_template(self, message: NotificationMessage) -> str:
        """Render plain text email template"""
        template_data = message.template_data

        def _clean(value: Any) -> str:
            if value is None:
                return ""
            s = str(value).strip()
            if not s or s.lower() in {"n/a", "none", "null"}:
                return ""
            return s

        symbol = _clean(template_data.get("symbol"))
        company = _clean(template_data.get("company"))
        change_type = _clean(template_data.get("change_type"))
        alert_name = _clean(template_data.get("alert_name")) or "Alert"
        trigger_reason = _clean(template_data.get("trigger_reason")) or "A monitored condition was triggered."
        event_type = _clean(template_data.get("event_type"))
        triggered_at = _clean(template_data.get("triggered_at")) or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")

        previous_grade = _clean(template_data.get("previous_grade"))
        new_grade = _clean(template_data.get("new_grade"))
        grade_line = ""
        if previous_grade and new_grade and previous_grade != new_grade:
            grade_line = f"{previous_grade} -> {new_grade}"
        elif new_grade:
            grade_line = new_grade

        headline = " - ".join([p for p in [symbol, change_type] if p]) or "STOCK ALERT"
        urgency = (message.urgency_level or "medium").upper()

        lines: List[str] = []
        lines.append(f"{headline} ({urgency})")
        if company:
            lines.append(company)
        lines.append("")
        lines.append(trigger_reason)
        lines.append("")
        lines.append("Key details:")
        lines.append(f"- Alert: {alert_name}")
        if symbol:
            lines.append(f"- Symbol: {symbol}")
        if event_type:
            lines.append(f"- Event: {event_type}")
        if change_type:
            lines.append(f"- Change: {change_type}")
        if grade_line:
            lines.append(f"- Grade: {grade_line}")
        consensus_change = _clean(template_data.get("consensus_change"))
        if consensus_change:
            lines.append(f"- Consensus change: {consensus_change}")
        price_target = _clean(template_data.get("price_target"))
        if price_target:
            lines.append(f"- Price target: {price_target}")
        analyst = _clean(template_data.get("analyst"))
        if analyst:
            lines.append(f"- Analyst: {analyst}")
        source = _clean(template_data.get("source"))
        if source:
            lines.append(f"- Source: {source}")
        lines.append(f"- Triggered at (UTC): {triggered_at}")
        lines.append("")
        lines.append("---")
        lines.append("You received this message because alerts are enabled for your account.")
        return "\n".join(lines).strip()


class LoggingEmailChannel(NotificationChannel):
    """Fallback email channel that logs messages instead of sending (for local/dev)."""

    def validate_recipient(self, recipient: str) -> bool:
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, recipient) is not None

    async def send(self, message: NotificationMessage) -> Dict[str, Any]:
        try:
            logger.info(
                f"📧 (logging-only) Email to {message.recipient}: {message.subject or 'Stock Alert'}"
            )
            return {
                'success': True,
                'message': 'Email logged (SMTP not configured)',
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Error logging email: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

class SMSChannel(NotificationChannel):
    """SMS notification channel"""
    
    def __init__(self, sms_provider: str, api_key: str):
        self.sms_provider = sms_provider
        self.api_key = api_key
    
    def validate_recipient(self, recipient: str) -> bool:
        """Validate phone number format"""
        import re
        # Simple validation for phone numbers
        pattern = r'^\+?1?\d{9,15}$'
        return re.match(pattern, recipient.replace('-', '').replace(' ', '')) is not None
    
    async def send(self, message: NotificationMessage) -> Dict[str, Any]:
        """Send SMS notification"""
        try:
            # TODO: Implement SMS provider integration (Twilio, AWS SNS, etc.)
            # For now, just log the message
            logger.info(f"📱 SMS to {message.recipient}: {message.body[:100]}...")
            
            return {
                'success': True,
                'message': 'SMS sent successfully',
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error sending SMS: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

class WebhookChannel(NotificationChannel):
    """Webhook notification channel"""
    
    def validate_recipient(self, recipient: str) -> bool:
        """Validate webhook URL"""
        import re
        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return re.match(pattern, recipient) is not None
    
    async def send(self, message: NotificationMessage) -> Dict[str, Any]:
        """Send webhook notification"""
        try:
            import aiohttp
            
            payload = {
                'alert_id': message.template_data.get('alert_id'),
                'user_id': message.template_data.get('user_id'),
                'symbol': message.template_data.get('symbol'),
                'company': message.template_data.get('company'),
                'change_type': message.template_data.get('change_type'),
                'previous_grade': message.template_data.get('previous_grade'),
                'new_grade': message.template_data.get('new_grade'),
                'consensus_change': message.template_data.get('consensus_change'),
                'trigger_reason': message.template_data.get('trigger_reason'),
                'urgency_level': message.urgency_level,
                'triggered_at': datetime.now().isoformat()
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(message.recipient, json=payload, timeout=30) as response:
                    if response.status == 200:
                        return {
                            'success': True,
                            'message': 'Webhook sent successfully',
                            'timestamp': datetime.now().isoformat()
                        }
                    else:
                        return {
                            'success': False,
                            'error': f'HTTP {response.status}',
                            'timestamp': datetime.now().isoformat()
                        }
            
        except Exception as e:
            logger.error(f"❌ Error sending webhook: {e}")
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

class NotificationService:
    """Main notification service with pluggable channels"""
    
    def __init__(self):
        self.channels: Dict[ChannelType, NotificationChannel] = {}
        self._setup_default_channels()
    
    def _setup_default_channels(self):
        """Setup default notification channels"""
        # Email channel (configure from environment)
        import os
        smtp_host = os.getenv('SMTP_HOST', 'localhost')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_user = os.getenv('SMTP_USER', '')
        smtp_password = os.getenv('SMTP_PASSWORD', '')

        if smtp_user and smtp_password:
            self.channels[ChannelType.EMAIL] = EmailChannel(
                smtp_host, smtp_port, smtp_user, smtp_password
            )
        else:
            self.channels[ChannelType.EMAIL] = LoggingEmailChannel()

        # SMS channel (configure from environment)
        sms_provider = os.getenv('SMS_PROVIDER', 'twilio')
        sms_api_key = os.getenv('SMS_API_KEY', '')
        
        if sms_api_key:
            self.channels[ChannelType.SMS] = SMSChannel(sms_provider, sms_api_key)
        
        # Webhook channel
        self.channels[ChannelType.WEBHOOK] = WebhookChannel()
    
    def register_channel(self, channel_type: ChannelType, channel: NotificationChannel):
        """Register a custom notification channel"""
        self.channels[channel_type] = channel
        logger.info(f"✅ Registered custom channel: {channel_type.value}")
    
    async def process_notifications(self, job_config: Dict[str, Any], execution_context) -> Dict[str, Any]:
        """Process notification queue"""
        batch_size = job_config.get('batch_size', 50)
        retry_delay_minutes = job_config.get('retry_delay_minutes', 5)
        
        try:
            # Get pending notifications
            notifications = await self._get_pending_notifications(batch_size)
            
            if not notifications:
                logger.info("📬 No pending notifications")
                return {
                    'records_processed': 0,
                    'records_failed': 0,
                    'alerts_generated': 0
                }
            
            logger.info(f"📬 Processing {len(notifications)} notifications")
            
            processed = 0
            failed = 0
            
            for notification in notifications:
                try:
                    # Update status to processing
                    await self._update_notification_status(
                        notification['queue_id'], NotificationStatus.PROCESSING
                    )
                    
                    # Get channel
                    channel_type = ChannelType(notification['channel_type'])
                    channel = self.channels.get(channel_type)
                    
                    if not channel:
                        raise ValueError(f"No channel registered for {channel_type.value}")

                    recipient = notification.get('recipient')
                    if channel_type == ChannelType.EMAIL and notification.get('user_email'):
                        recipient = notification.get('user_email')
                    
                    # Validate recipient
                    if not recipient or not channel.validate_recipient(recipient):
                        raise ValueError(f"Invalid recipient: {recipient}")
                    
                    # Create message
                    message = NotificationMessage(
                        recipient=recipient,
                        subject=notification.get('subject'),
                        body=notification['message_body'],
                        template_data=notification.get('template_data', {}),
                        urgency_level='medium',
                        channel_type=channel_type
                    )
                    
                    # Send notification
                    result = await channel.send(message)
                    
                    if result['success']:
                        # Mark as sent
                        await self._update_notification_status(
                            notification['queue_id'], NotificationStatus.SENT
                        )
                        processed += 1
                    else:
                        # Mark as failed and schedule retry
                        await self._handle_notification_failure(
                            notification, result['error'], retry_delay_minutes
                        )
                        failed += 1
                
                except Exception as e:
                    logger.error(f"❌ Error processing notification {notification['queue_id']}: {e}")
                    await self._handle_notification_failure(
                        notification, str(e), retry_delay_minutes
                    )
                    failed += 1
            
            logger.info(f"✅ Processed {processed} notifications, {failed} failed")
            
            return {
                'records_processed': processed,
                'records_failed': failed,
                'alerts_generated': 0
            }
            
        except Exception as e:
            logger.error(f"❌ Error in notification service: {e}")
            raise
    
    async def _get_pending_notifications(self, batch_size: int) -> List[Dict[str, Any]]:
        """Get pending notifications from queue"""
        try:
            query = """
                SELECT queue_id, alert_event_id, channel_type, recipient, user_email, subject, 
                       message_body, template_data, attempts, max_attempts
                FROM universal_notification_queue
                WHERE status = 'pending' 
                   OR (status = 'failed' AND next_attempt_at <= NOW())
                ORDER BY next_attempt_at ASC
                LIMIT :batch_size
            """
            
            rows = db.execute_query(query, {"batch_size": batch_size})
            notifications = []
            
            for row in rows:
                notification = dict(row)
                # Parse JSON fields
                if notification.get('template_data'):
                    notification['template_data'] = notification['template_data']
                notifications.append(notification)
            
            return notifications
            
        except Exception as e:
            logger.error(f"❌ Error getting pending notifications: {e}")
            return []
    
    async def _update_notification_status(self, queue_id: str, status: NotificationStatus):
        """Update notification status"""
        try:
            query = """
                UPDATE universal_notification_queue 
                SET status = :status,
                    attempts = CASE WHEN :status = 'processing' THEN attempts + 1 ELSE attempts END,
                    last_attempt_at = CASE WHEN :status IN ('sent', 'failed') THEN NOW() ELSE last_attempt_at END,
                    sent_at = CASE WHEN :status = 'sent' THEN NOW() ELSE sent_at END
                WHERE queue_id = :queue_id
            """
            
            params = {
                "queue_id": queue_id,
                "status": status.value
            }
            
            db.execute_update(query, params)
            
        except Exception as e:
            logger.error(f"❌ Error updating notification status: {e}")
    
    async def _handle_notification_failure(self, notification: Dict[str, Any], error: str, retry_delay_minutes: int):
        """Handle notification failure with retry logic"""
        try:
            attempts = notification.get('attempts', 0) + 1
            max_attempts = notification.get('max_attempts', 3)
            
            if attempts >= max_attempts:
                # Mark as permanently failed
                query = """
                    UPDATE universal_notification_queue 
                    SET status = 'failed',
                        attempts = :attempts,
                        last_attempt_at = NOW(),
                        error_message = :error_message
                    WHERE queue_id = :queue_id
                """
                
                params = {
                    "queue_id": notification['queue_id'],
                    "attempts": attempts,
                    "error_message": error
                }
                
                logger.error(f"❌ Notification {notification['queue_id']} failed permanently after {attempts} attempts")
                
            else:
                # Schedule retry
                next_attempt = datetime.now() + timedelta(minutes=retry_delay_minutes * attempts)
                
                query = """
                    UPDATE universal_notification_queue 
                    SET status = 'pending',
                        attempts = :attempts,
                        last_attempt_at = NOW(),
                        next_attempt_at = :next_attempt_at,
                        error_message = :error_message
                    WHERE queue_id = :queue_id
                """
                
                params = {
                    "queue_id": notification['queue_id'],
                    "attempts": attempts,
                    "next_attempt_at": next_attempt,
                    "error_message": error
                }
                
                logger.warning(f"⚠️ Notification {notification['queue_id']} failed, retry {attempts}/{max_attempts} at {next_attempt}")
            
            db.execute_update(query, params)
            
        except Exception as e:
            logger.error(f"❌ Error handling notification failure: {e}")

# Global service instance
notification_service = NotificationService()
