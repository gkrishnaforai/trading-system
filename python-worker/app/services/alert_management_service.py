"""
Alert Management Service - Handles user alert creation and management
Follows SOLID principles: Single Responsibility, Open/Closed
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import json
import uuid

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("alert_management_service")


@dataclass
class AlertDefinition:
    """Alert definition structure"""
    alert_id: str
    user_id: str
    stock_symbol: Optional[str]
    alert_type: str
    name: str
    enabled: bool = True
    config: Dict[str, Any] = None
    notification_channels: List[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}
        if self.notification_channels is None:
            self.notification_channels = ['email']
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


@dataclass
class AlertSubscription:
    """Alert subscription for rating updates"""
    user_id: str
    symbol: str
    subscription_type: str
    enabled: bool = True
    priority: int = 2
    config: Dict[str, Any] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}
        if self.created_at is None:
            self.created_at = datetime.now()


class AlertRepository(ABC):
    """Abstract repository for alert data"""
    
    @abstractmethod
    def create_alert(self, alert: AlertDefinition) -> bool:
        """Create a new alert"""
        pass
    
    @abstractmethod
    def update_alert(self, alert: AlertDefinition) -> bool:
        """Update an existing alert"""
        pass
    
    @abstractmethod
    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """Delete an alert"""
        pass
    
    @abstractmethod
    def get_user_alerts(self, user_id: str, alert_type: str = None) -> List[AlertDefinition]:
        """Get alerts for a user"""
        pass
    
    @abstractmethod
    def get_alert(self, alert_id: str, user_id: str) -> Optional[AlertDefinition]:
        """Get a specific alert"""
        pass


class PostgresAlertRepository(AlertRepository):
    """PostgreSQL implementation of alert repository"""
    
    def create_alert(self, alert: AlertDefinition) -> bool:
        """Create a new alert in the database"""
        try:
            query = """
                INSERT INTO alerts (
                    alert_id, user_id, stock_symbol, alert_type_id, name, 
                    enabled, config, notification_channels, created_at, updated_at
                ) VALUES (:alert_id, :user_id, :stock_symbol, :alert_type_id, :name, 
                        :enabled, :config, :notification_channels, :created_at, :updated_at)
            """
            
            params = {
                "alert_id": alert.alert_id,
                "user_id": alert.user_id,
                "stock_symbol": alert.stock_symbol,
                "alert_type_id": alert.alert_type,
                "name": alert.name,
                "enabled": alert.enabled,
                "config": json.dumps(alert.config),
                "notification_channels": ','.join(alert.notification_channels),
                "created_at": alert.created_at,
                "updated_at": alert.updated_at
            }
            
            result = db.execute_update(query, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ Error creating alert: {e}")
            return False
    
    def update_alert(self, alert: AlertDefinition) -> bool:
        """Update an existing alert"""
        try:
            query = """
                UPDATE alerts 
                SET name = :name, enabled = :enabled, config = :config, notification_channels = :notification_channels, updated_at = :updated_at
                WHERE alert_id = :alert_id AND user_id = :user_id
            """
            
            params = {
                "name": alert.name,
                "enabled": alert.enabled,
                "config": json.dumps(alert.config),
                "notification_channels": ','.join(alert.notification_channels),
                "updated_at": datetime.now(),
                "alert_id": alert.alert_id,
                "user_id": alert.user_id
            }
            
            result = db.execute_update(query, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ Error updating alert {alert.alert_id}: {e}")
            return False
    
    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """Delete an alert"""
        try:
            query = "DELETE FROM alerts WHERE alert_id = :alert_id AND user_id = :user_id"
            params = {"alert_id": alert_id, "user_id": user_id}
            
            db.execute_update(query, params)
            logger.info(f"✅ Deleted alert {alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting alert {alert_id}: {e}")
            return False
    
    def get_user_alerts(self, user_id: str, alert_type: str = None) -> List[AlertDefinition]:
        """Get alerts for a user"""
        try:
            if alert_type:
                query = """
                    SELECT alert_id, user_id, stock_symbol, alert_type_id, name, 
                           enabled, config, notification_channels, created_at, updated_at
                    FROM alerts 
                    WHERE user_id = :user_id AND alert_type_id = :alert_type
                    ORDER BY created_at DESC
                """
                params = {"user_id": user_id, "alert_type": alert_type}
            else:
                query = """
                    SELECT alert_id, user_id, stock_symbol, alert_type_id, name, 
                           enabled, config, notification_channels, created_at, updated_at
                    FROM alerts 
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                """
                params = {"user_id": user_id}
            
            rows = db.execute_query(query, params)
            
            alerts = []
            for row in rows:
                config = row.get('config', {})  # Already a dict from JSONB
                notification_channels = row['notification_channels'].split(',') if row.get('notification_channels') else ['email']
                
                alert = AlertDefinition(
                    alert_id=row['alert_id'],
                    user_id=str(row['user_id']),  # Convert UUID to string
                    stock_symbol=row['stock_symbol'],
                    alert_type=row['alert_type_id'],
                    name=row['name'],
                    enabled=row['enabled'],
                    config=config,
                    notification_channels=notification_channels,
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                alerts.append(alert)
            
            return alerts
            
        except Exception as e:
            logger.error(f"❌ Error getting user alerts: {e}")
            return []
    
    def get_alert(self, alert_id: str, user_id: str) -> Optional[AlertDefinition]:
        """Get a specific alert"""
        try:
            query = """
                SELECT alert_id, user_id, stock_symbol, alert_type_id, name, 
                       enabled, config, notification_channels, created_at, updated_at
                FROM alerts 
                WHERE alert_id = :alert_id AND user_id = :user_id
            """
            
            params = {"alert_id": alert_id, "user_id": user_id}
            
            rows = db.execute_query(query, params)
            
            if not rows:
                return None
            
            row = rows[0]
            config = row.get('config', {})  # Already a dict from JSONB
            notification_channels = row['notification_channels'].split(',') if row.get('notification_channels') else ['email']
            
            return AlertDefinition(
                alert_id=row['alert_id'],
                user_id=str(row['user_id']),  # Convert UUID to string
                stock_symbol=row['stock_symbol'],
                alert_type=row['alert_type_id'],
                name=row['name'],
                enabled=row['enabled'],
                config=config,
                notification_channels=notification_channels,
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            
        except Exception as e:
            logger.error(f"❌ Error getting alert {alert_id}: {e}")
            return None


class RatingSubscriptionRepository:
    """Repository for rating subscriptions"""
    
    async def create_subscription(self, subscription: AlertSubscription) -> bool:
        """Create a new rating subscription"""
        try:
            query = """
                INSERT INTO rating_subscriptions (
                    user_id, symbol, subscription_type, enabled, priority, config, created_at
                ) VALUES (:user_id, :symbol, :subscription_type, :enabled, :priority, :config, :created_at)
                ON CONFLICT (user_id, symbol, subscription_type) 
                DO UPDATE SET 
                    enabled = EXCLUDED.enabled,
                    priority = EXCLUDED.priority,
                    config = EXCLUDED.config,
                    updated_at = NOW()
            """
            
            params = {
                "user_id": subscription.user_id,
                "symbol": subscription.symbol,
                "subscription_type": subscription.subscription_type,
                "enabled": subscription.enabled,
                "priority": subscription.priority,
                "config": json.dumps(subscription.config),
                "created_at": subscription.created_at
            }
            
            result = db.execute_update(query, params)
            return result > 0
            
        except Exception as e:
            logger.error(f"❌ Error creating subscription: {e}")
            return False
    
    async def get_user_subscriptions(self, user_id: str, subscription_type: str = None) -> List[AlertSubscription]:
        """Get user's rating subscriptions"""
        try:
            if subscription_type:
                query = """
                    SELECT user_id, symbol, subscription_type, enabled, priority, config, created_at
                    FROM rating_subscriptions 
                    WHERE user_id = :user_id AND subscription_type = :subscription_type
                    ORDER BY created_at DESC
                """
                params = {"user_id": user_id, "subscription_type": subscription_type}
            else:
                query = """
                    SELECT user_id, symbol, subscription_type, enabled, priority, config, created_at
                    FROM rating_subscriptions 
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC
                """
                params = {"user_id": user_id}
            
            rows = db.execute_query(query, params)
            
            subscriptions = []
            for row in rows:
                config = json.loads(row[5]) if row[5] else {}
                
                subscription = AlertSubscription(
                    user_id=row[0],
                    symbol=row[1],
                    subscription_type=row[2],
                    enabled=row[3],
                    priority=row[4],
                    config=config,
                    created_at=row[6]
                )
                subscriptions.append(subscription)
            
            return subscriptions
            
        except Exception as e:
            logger.error(f"❌ Error getting subscriptions: {e}")
            return []
    
    async def get_symbols_for_subscription_type(self, subscription_type: str) -> Set[str]:
        """Get all symbols subscribed to a specific type"""
        try:
            query = """
                SELECT DISTINCT symbol
                FROM rating_subscriptions 
                WHERE subscription_type = :subscription_type AND enabled = TRUE
            """
            
            params = {"subscription_type": subscription_type}
            
            rows = db.execute_query(query, params)
            return {row[0] for row in rows}
            
        except Exception as e:
            logger.error(f"❌ Error getting symbols for {subscription_type}: {e}")
            return set()


class AlertManagementService:
    """Main alert management service"""
    
    def __init__(self, alert_repo: AlertRepository = None):
        self.alert_repository = alert_repo or PostgresAlertRepository()
        self.subscription_repo = RatingSubscriptionRepository()
    
    def create_rating_alert(self, user_id: str, stock_symbol: str, alert_type: str, 
                                name: str, config: Dict[str, Any] = None,
                                notification_channels: List[str] = None) -> Optional[str]:
        """Create a new rating alert"""
        try:
            # Validate alert type
            valid_types = ['rating_change', 'price_target_change', 'consensus_alert', 'earnings_alert']
            if alert_type not in valid_types:
                logger.error(f"❌ Invalid alert type: {alert_type}")
                return None
            
            # Generate alert ID
            alert_id = str(uuid.uuid4())
            
            # Create alert definition
            alert = AlertDefinition(
                alert_id=alert_id,
                user_id=user_id,
                stock_symbol=stock_symbol.upper(),
                alert_type=alert_type,
                name=name,
                config=config or {},
                notification_channels=notification_channels or ['email']
            )
            
            # Save to database
            success = self.alert_repository.create_alert(alert)
            
            if success:
                logger.info(f"✅ Created alert {alert_id} for {stock_symbol}")
                return alert_id
            else:
                logger.error(f"❌ Failed to create alert for {stock_symbol}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error creating rating alert: {e}")
            return None
    
    async def update_alert(self, alert_id: str, user_id: str, name: str = None,
                          enabled: bool = None, config: Dict[str, Any] = None,
                          notification_channels: List[str] = None) -> bool:
        """Update an existing alert"""
        try:
            # Get existing alert
            alert = self.alert_repository.get_alert(alert_id, user_id)
            if not alert:
                logger.error(f"❌ Alert {alert_id} not found")
                return False
            
            # Update fields
            if name is not None:
                alert.name = name
            if enabled is not None:
                alert.enabled = enabled
            if config is not None:
                alert.config = config
            if notification_channels is not None:
                alert.notification_channels = notification_channels
            
            # Save changes
            success = self.alert_repository.update_alert(alert)
            
            if success:
                logger.info(f"✅ Updated alert {alert_id}")
            else:
                logger.error(f"❌ Failed to update alert {alert_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error updating alert {alert_id}: {e}")
            return False
    
    def delete_alert(self, alert_id: str, user_id: str) -> bool:
        """Delete an alert"""
        try:
            success = self.alert_repository.delete_alert(alert_id, user_id)
            
            if success:
                logger.info(f"✅ Deleted alert {alert_id}")
            else:
                logger.error(f"❌ Failed to delete alert {alert_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Error deleting alert {alert_id}: {e}")
            return False
    
    def get_user_alerts(self, user_id: str, alert_type: str = None) -> List[AlertDefinition]:
        """Get all alerts for a user"""
        try:
            return self.alert_repository.get_user_alerts(user_id, alert_type)
        except Exception as e:
            logger.error(f"❌ Error getting user alerts: {e}")
            return []
    
    def get_alert(self, alert_id: str, user_id: str) -> Optional[AlertDefinition]:
        """Get a specific alert"""
        try:
            return self.alert_repository.get_alert(alert_id, user_id)
        except Exception as e:
            logger.error(f"❌ Error getting alert {alert_id}: {e}")
            return None
    
    async def subscribe_to_rating_updates(self, user_id: str, symbols: List[str],
                                        subscription_type: str = 'rating_updates',
                                        priority: int = 2, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Subscribe user to rating updates for multiple symbols"""
        try:
            results = {'success': [], 'failed': [], 'total': len(symbols)}
            
            for symbol in symbols:
                subscription = AlertSubscription(
                    user_id=user_id,
                    symbol=symbol.upper(),
                    subscription_type=subscription_type,
                    priority=priority,
                    config=config or {}
                )
                
                success = await self.subscription_repo.create_subscription(subscription)
                
                if success:
                    results['success'].append(symbol)
                else:
                    results['failed'].append(symbol)
            
            logger.info(f"📊 Subscription complete: {len(results['success'])}/{results['total']} successful")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error in subscription: {e}")
            return {'success': [], 'failed': symbols, 'total': len(symbols)}
    
    async def get_user_subscriptions(self, user_id: str, subscription_type: str = None) -> List[AlertSubscription]:
        """Get user's rating subscriptions"""
        try:
            return await self.subscription_repo.get_user_subscriptions(user_id, subscription_type)
        except Exception as e:
            logger.error(f"❌ Error getting user subscriptions: {e}")
            return []
    
    async def get_alert_summary(self, user_id: str) -> Dict[str, Any]:
        """Get alert summary for a user"""
        try:
            # Get all alerts
            alerts = await self.get_user_alerts(user_id)
            
            # Get all subscriptions
            subscriptions = await self.get_user_subscriptions(user_id)
            
            # Count by type
            alert_counts = {}
            for alert in alerts:
                alert_type = alert.alert_type
                if alert_type not in alert_counts:
                    alert_counts[alert_type] = {'total': 0, 'enabled': 0}
                alert_counts[alert_type]['total'] += 1
                if alert.enabled:
                    alert_counts[alert_type]['enabled'] += 1
            
            # Count subscriptions by type
            subscription_counts = {}
            for sub in subscriptions:
                sub_type = sub.subscription_type
                if sub_type not in subscription_counts:
                    subscription_counts[sub_type] = {'total': 0, 'enabled': 0}
                subscription_counts[sub_type]['total'] += 1
                if sub.enabled:
                    subscription_counts[sub_type]['enabled'] += 1
            
            return {
                'alerts': {
                    'total': len(alerts),
                    'enabled': len([a for a in alerts if a.enabled]),
                    'by_type': alert_counts
                },
                'subscriptions': {
                    'total': len(subscriptions),
                    'enabled': len([s for s in subscriptions if s.enabled]),
                    'by_type': subscription_counts,
                    'unique_symbols': len(set(s.symbol for s in subscriptions))
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting alert summary: {e}")
            return {}
    
    def create_alert_for_symbol(self, base_alert_id: str, user_id: str, alert_request: 'RatingAlertRequest') -> bool:
        """Create a new alert for a specific symbol based on an existing alert"""
        try:
            # Get the base alert to copy configuration
            base_alert = self.alert_repository.get_alert(base_alert_id, user_id)
            if not base_alert:
                return False
            
            # Create new alert with the same configuration but different symbol
            new_alert = AlertDefinition(
                alert_id=str(uuid.uuid4()),
                user_id=user_id,
                stock_symbol=alert_request.stock_symbol,
                alert_type=base_alert.alert_type,
                name=f"{base_alert.name} - {alert_request.stock_symbol}",
                enabled=base_alert.enabled,
                config=base_alert.config,
                notification_channels=base_alert.notification_channels,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            return self.alert_repository.create_alert(new_alert)
            
        except Exception as e:
            logger.error(f"❌ Error creating alert for symbol {alert_request.stock_symbol}: {e}")
            return False
    
    def delete_alert_for_symbol(self, base_alert_id: str, user_id: str, symbol: str) -> bool:
        """Delete alert for a specific symbol"""
        try:
            # Find the alert for this symbol
            alerts = self.alert_repository.get_user_alerts(user_id)
            target_alert = None
            
            for alert in alerts:
                if (alert.stock_symbol == symbol and 
                    alert.alert_type in ['rating_change', 'price_target_change', 'consensus_alert', 'earnings_alert']):
                    target_alert = alert
                    break
            
            if target_alert:
                return self.alert_repository.delete_alert(target_alert.alert_id, user_id)
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Error deleting alert for symbol {symbol}: {e}")
            return False
    
    def get_alert_symbols(self, alert_id: str, user_id: str) -> List[str]:
        """Get all symbols for alerts of the same type"""
        try:
            # Get the base alert
            base_alert = self.alert_repository.get_alert(alert_id, user_id)
            if not base_alert:
                return []
            
            # Get all alerts of the same type for this user
            alerts = self.alert_repository.get_user_alerts(user_id, base_alert.alert_type)
            symbols = [alert.stock_symbol for alert in alerts]
            
            return sorted(list(set(symbols)))  # Remove duplicates and sort
            
        except Exception as e:
            logger.error(f"❌ Error getting symbols for alert {alert_id}: {e}")
            return []


# Global service instance
alert_management_service = AlertManagementService()
