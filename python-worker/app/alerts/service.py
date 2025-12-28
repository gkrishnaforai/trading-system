"""
Alert Service
Manages alerts, evaluation, and notifications
Industry Standard: Service layer with clear separation of concerns
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.database import db
from app.alerts.base import (
    BaseAlertPlugin, AlertContext, AlertResult,
    NotificationChannel, AlertSeverity
)
from app.alerts.registry import get_alert_registry
from app.exceptions import AlertNotificationError, ValidationError, DatabaseError

logger = logging.getLogger(__name__)


class AlertService:
    """
    Service for managing alerts
    
    Responsibilities:
    - CRUD operations for alerts
    - Alert evaluation
    - Notification sending
    - Alert history tracking
    
    SOLID: Single Responsibility - manages alerts only
    """
    
    def __init__(self):
        self.registry = get_alert_registry()
        self._initialize_default_plugins()
    
    def _initialize_default_plugins(self):
        """Initialize default alert plugins"""
        from app.alerts.plugins.email_alert import EmailAlertPlugin
        from app.alerts.plugins.sms_alert import SMSAlertPlugin
        
        # Register default plugins
        self.registry.register(EmailAlertPlugin, "email_alert")
        self.registry.register(SMSAlertPlugin, "sms_alert")
        
        logger.info("✅ Default alert plugins initialized")
    
    # ==================== Alert CRUD ====================
    
    def create_alert(
        self,
        user_id: str,
        alert_type_id: str,
        name: str,
        config: Dict[str, Any],
        notification_channels: List[str],
        portfolio_id: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        enabled: bool = True
    ) -> str:
        """
        Create a new alert
        
        Args:
            user_id: User ID
            alert_type_id: Alert type identifier
            name: Alert name
            config: Alert configuration
            notification_channels: List of channels (['email', 'sms'])
            portfolio_id: Portfolio ID (optional, for portfolio-level alerts)
            stock_symbol: Stock symbol (optional, for stock-level alerts)
            enabled: Whether alert is enabled
        
        Returns:
            Alert ID
        
        Raises:
            ValidationError: If validation fails
            DatabaseError: If database operation fails
        """
        # Validate
        if not portfolio_id and not stock_symbol:
            raise ValidationError("Either portfolio_id or stock_symbol must be provided")
        
        if portfolio_id and stock_symbol:
            raise ValidationError("Cannot specify both portfolio_id and stock_symbol")
        
        # Validate alert type exists
        alert_type = self._get_alert_type(alert_type_id)
        if not alert_type:
            raise ValidationError(f"Alert type '{alert_type_id}' not found")
        
        # Validate plugin exists
        plugin = self.registry.get(alert_type['plugin_name'])
        if not plugin:
            raise ValidationError(f"Alert plugin '{alert_type['plugin_name']}' not found")
        
        # Validate config
        plugin.validate_config({**config, "alert_type": alert_type_id})
        
        # Generate alert ID
        alert_id = str(uuid.uuid4())
        
        # Insert alert
        query = """
            INSERT INTO alerts 
            (alert_id, user_id, portfolio_id, stock_symbol, alert_type_id, name, enabled, config, notification_channels)
            VALUES (:alert_id, :user_id, :portfolio_id, :stock_symbol, :alert_type_id, :name, :enabled, :config, :channels)
        """
        
        try:
            import json
            db.execute_update(query, {
                "alert_id": alert_id,
                "user_id": user_id,
                "portfolio_id": portfolio_id,
                "stock_symbol": stock_symbol,
                "alert_type_id": alert_type_id,
                "name": name,
                "enabled": enabled,
                "config": json.dumps({**config, "alert_type": alert_type_id}),
                "channels": ",".join(notification_channels)
            })
            
            logger.info(f"✅ Created alert: {alert_id} for user {user_id}")
            return alert_id
            
        except Exception as e:
            logger.error(f"Failed to create alert: {e}", exc_info=True)
            raise DatabaseError(f"Failed to create alert: {str(e)}") from e
    
    def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        """Get alert by ID"""
        query = """
            SELECT * FROM alerts WHERE alert_id = :alert_id
        """
        
        results = db.execute_query(query, {"alert_id": alert_id})
        if not results:
            return None
        
        alert = results[0]
        # Parse JSON config
        import json
        alert['config'] = json.loads(alert['config']) if alert.get('config') else {}
        alert['notification_channels'] = alert.get('notification_channels', '').split(',')
        
        return alert
    
    def list_alerts(
        self,
        user_id: str,
        portfolio_id: Optional[str] = None,
        stock_symbol: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        """List alerts for user"""
        query = """
            SELECT * FROM alerts 
            WHERE user_id = :user_id
        """
        params = {"user_id": user_id}
        
        if portfolio_id:
            query += " AND portfolio_id = :portfolio_id"
            params["portfolio_id"] = portfolio_id
        elif stock_symbol:
            query += " AND stock_symbol = :stock_symbol"
            params["stock_symbol"] = stock_symbol
        
        if enabled_only:
            query += " AND enabled = 1"
        
        query += " ORDER BY created_at DESC"
        
        results = db.execute_query(query, params)
        
        # Parse JSON configs
        import json
        for alert in results:
            alert['config'] = json.loads(alert['config']) if alert.get('config') else {}
            alert['notification_channels'] = alert.get('notification_channels', '').split(',')
        
        return results
    
    def update_alert(
        self,
        alert_id: str,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        notification_channels: Optional[List[str]] = None,
        enabled: Optional[bool] = None
    ) -> bool:
        """Update alert"""
        # Get existing alert
        alert = self.get_alert(alert_id)
        if not alert:
            raise ValidationError(f"Alert '{alert_id}' not found")
        
        # Build update query
        updates = []
        params = {"alert_id": alert_id}
        
        if name is not None:
            updates.append("name = :name")
            params["name"] = name
        
        if config is not None:
            import json
            # Merge with existing config
            existing_config = alert.get('config', {})
            merged_config = {**existing_config, **config}
            updates.append("config = :config")
            params["config"] = json.dumps(merged_config)
        
        if notification_channels is not None:
            updates.append("notification_channels = :channels")
            params["channels"] = ",".join(notification_channels)
        
        if enabled is not None:
            updates.append("enabled = :enabled")
            params["enabled"] = enabled
        
        if not updates:
            return True  # No updates
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        query = f"""
            UPDATE alerts 
            SET {', '.join(updates)}
            WHERE alert_id = :alert_id
        """
        
        try:
            db.execute_update(query, params)
            logger.info(f"✅ Updated alert: {alert_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update alert: {e}", exc_info=True)
            raise DatabaseError(f"Failed to update alert: {str(e)}") from e
    
    def delete_alert(self, alert_id: str) -> bool:
        """Delete alert"""
        query = "DELETE FROM alerts WHERE alert_id = :alert_id"
        
        try:
            rows = db.execute_update(query, {"alert_id": alert_id})
            if rows > 0:
                logger.info(f"✅ Deleted alert: {alert_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete alert: {e}", exc_info=True)
            raise DatabaseError(f"Failed to delete alert: {str(e)}") from e
    
    # ==================== Alert Evaluation ====================
    
    def evaluate_alerts(
        self,
        user_id: str,
        context: AlertContext
    ) -> List[AlertResult]:
        """
        Evaluate all enabled alerts for a user/portfolio/stock
        
        Args:
            user_id: User ID
            context: Alert context with current data
        
        Returns:
            List of alert results
        """
        # Get relevant alerts
        alerts = self.list_alerts(
            user_id=user_id,
            portfolio_id=context.portfolio_id,
            stock_symbol=context.stock_symbol,
            enabled_only=True
        )
        
        results = []
        for alert in alerts:
            try:
                result = self._evaluate_alert(alert, context)
                if result.triggered:
                    results.append(result)
                    # Send notifications
                    self._send_notifications(alert, result, context)
            except Exception as e:
                logger.error(f"Error evaluating alert {alert['alert_id']}: {e}", exc_info=True)
                # Continue with other alerts (fail-fast per alert, not all)
        
        return results
    
    def _evaluate_alert(
        self,
        alert: Dict[str, Any],
        context: AlertContext
    ) -> AlertResult:
        """Evaluate a single alert"""
        alert_type_id = alert['alert_type_id']
        config = alert.get('config', {})
        
        # Get alert type
        alert_type = self._get_alert_type(alert_type_id)
        if not alert_type:
            raise ValidationError(f"Alert type '{alert_type_id}' not found")
        
        # Get plugin
        plugin = self.registry.get(alert_type['plugin_name'])
        if not plugin:
            raise ValidationError(f"Alert plugin '{alert_type['plugin_name']}' not found")
        
        # Evaluate
        return plugin.evaluate(context, config)
    
    def _send_notifications(
        self,
        alert: Dict[str, Any],
        result: AlertResult,
        context: AlertContext
    ):
        """Send notifications for triggered alert"""
        channels = alert.get('notification_channels', [])
        user_id = alert['user_id']
        
        # Get user notification channels
        user_channels = self._get_user_channels(user_id, channels)
        
        for channel_str in channels:
            try:
                channel = NotificationChannel(channel_str)
                recipients = user_channels.get(channel_str, [])
                
                if not recipients:
                    logger.warning(f"No recipients configured for {channel_str} for user {user_id}")
                    continue
                
                # Get plugin for channel
                plugin = self._get_plugin_for_channel(channel)
                if not plugin:
                    logger.warning(f"No plugin available for channel: {channel_str}")
                    continue
                
                # Send to all recipients
                for recipient in recipients:
                    try:
                        plugin.send_notification(
                            result, context, channel, recipient
                        )
                        # Record notification
                        self._record_notification(
                            alert, result, context, channel, recipient, "sent"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send {channel_str} to {recipient}: {e}")
                        self._record_notification(
                            alert, result, context, channel, recipient, "failed", str(e)
                        )
                        
            except ValueError:
                logger.warning(f"Invalid notification channel: {channel_str}")
            except Exception as e:
                logger.error(f"Error sending notification via {channel_str}: {e}", exc_info=True)
    
    def _get_plugin_for_channel(self, channel: NotificationChannel) -> Optional[BaseAlertPlugin]:
        """Get plugin that supports the channel"""
        # Try email plugin first
        if channel == NotificationChannel.EMAIL:
            return self.registry.get("email_alert")
        elif channel == NotificationChannel.SMS:
            return self.registry.get("sms_alert")
        # Future: push, webhook plugins
        
        return None
    
    def _record_notification(
        self,
        alert: Dict[str, Any],
        result: AlertResult,
        context: AlertContext,
        channel: NotificationChannel,
        recipient: str,
        status: str,
        error_message: Optional[str] = None
    ):
        """Record notification in database"""
        notification_id = str(uuid.uuid4())
        
        query = """
            INSERT INTO alert_notifications
            (notification_id, alert_id, user_id, portfolio_id, stock_symbol, alert_type_id,
             message, severity, channel, status, error_message, metadata)
            VALUES (:notification_id, :alert_id, :user_id, :portfolio_id, :stock_symbol, :alert_type_id,
                    :message, :severity, :channel, :status, :error_message, :metadata)
        """
        
        import json
        try:
            db.execute_update(query, {
                "notification_id": notification_id,
                "alert_id": alert['alert_id'],
                "user_id": alert['user_id'],
                "portfolio_id": context.portfolio_id,
                "stock_symbol": context.stock_symbol,
                "alert_type_id": alert['alert_type_id'],
                "message": result.message,
                "severity": result.severity.value,
                "channel": channel.value,
                "status": status,
                "error_message": error_message,
                "metadata": json.dumps(result.metadata or {})
            })
        except Exception as e:
            logger.error(f"Failed to record notification: {e}", exc_info=True)
    
    # ==================== Helper Methods ====================
    
    def _get_alert_type(self, alert_type_id: str) -> Optional[Dict[str, Any]]:
        """Get alert type from database"""
        query = "SELECT * FROM alert_types WHERE alert_type_id = :alert_type_id"
        results = db.execute_query(query, {"alert_type_id": alert_type_id})
        return results[0] if results else None
    
    def _get_user_channels(
        self,
        user_id: str,
        channel_types: List[str]
    ) -> Dict[str, List[str]]:
        """Get user notification channel addresses"""
        query = """
            SELECT channel_type, address 
            FROM notification_channels
            WHERE user_id = :user_id 
            AND channel_type IN ({})
            AND enabled = 1
            AND verified = 1
        """.format(','.join([f"'{ct}'" for ct in channel_types]))
        
        results = db.execute_query(query, {"user_id": user_id})
        
        channels = {}
        for row in results:
            channel_type = row['channel_type']
            if channel_type not in channels:
                channels[channel_type] = []
            channels[channel_type].append(row['address'])
        
        return channels

