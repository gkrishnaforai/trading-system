"""
Alert Subscription Service
Configurable alert subscription management system
Follows SOLID principles: Single Responsibility, Open/Closed
"""

import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json

from app.database import db
from app.observability.logging import get_logger

logger = get_logger("alert_subscription_service")


@dataclass
class AlertSubscription:
    """Alert subscription data structure"""
    symbol: str
    alert_type: str
    enabled: bool = True
    priority: int = 2
    config: Dict[str, Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}


@dataclass
class AlertType:
    """Alert type configuration"""
    alert_type: str
    name: str
    description: str
    default_config: Dict[str, Any]
    is_active: bool = True
    created_at: Optional[datetime] = None


class AlertSubscriptionService:
    """Service for managing alert subscriptions"""
    
    def __init__(self):
        self._cache_timeout = 300  # 5 minutes
        self._subscription_cache: Dict[str, List[AlertSubscription]] = {}
        self._cache_updated: Dict[str, datetime] = {}
    
    async def get_active_subscriptions(self, alert_type: str = None) -> List[AlertSubscription]:
        """Get active alert subscriptions with caching"""
        cache_key = f"subscriptions_{alert_type or 'all'}"
        
        # Check cache
        if (cache_key in self._subscription_cache and 
            cache_key in self._cache_updated and
            datetime.now() - self._cache_updated[cache_key] < timedelta(seconds=self._cache_timeout)):
            
            logger.debug(f"📋 Using cached subscriptions for {alert_type or 'all'}")
            return self._subscription_cache[cache_key]
        
        # Query database
        try:
            if alert_type:
                query = """
                    SELECT symbol, alert_type, enabled, priority, config, created_at, updated_at
                    FROM alert_subscriptions 
                    WHERE enabled = TRUE AND alert_type = $1
                    ORDER BY priority ASC, symbol ASC
                """
                params = [alert_type]
            else:
                query = """
                    SELECT symbol, alert_type, enabled, priority, config, created_at, updated_at
                    FROM alert_subscriptions 
                    WHERE enabled = TRUE
                    ORDER BY priority ASC, symbol ASC
                """
                params = []

            rows = db.execute_query_positional(query, params)
            
            subscriptions = []
            for row in rows:
                config = row[4] or {}
                if isinstance(config, str):
                    config = json.loads(config)
                
                subscription = AlertSubscription(
                    symbol=row[0],
                    alert_type=row[1],
                    enabled=row[2],
                    priority=row[3],
                    config=config,
                    created_at=row[5],
                    updated_at=row[6]
                )
                subscriptions.append(subscription)
            
            # Update cache
            self._subscription_cache[cache_key] = subscriptions
            self._cache_updated[cache_key] = datetime.now()
            
            logger.info(f"📋 Loaded {len(subscriptions)} active subscriptions for {alert_type or 'all'}")
            return subscriptions
            
        except Exception as e:
            logger.error(f"❌ Error loading subscriptions: {e}")
            return []
    
    async def get_symbols_for_alert_type(self, alert_type: str) -> Set[str]:
        """Get symbols subscribed to a specific alert type"""
        subscriptions = await self.get_active_subscriptions(alert_type)
        return {sub.symbol for sub in subscriptions}
    
    async def subscribe_symbol(self, symbol: str, alert_type: str, 
                              priority: int = 2, config: Dict[str, Any] = None) -> bool:
        """Subscribe a symbol to an alert type"""
        try:
            # Validate alert type
            if not await self._is_valid_alert_type(alert_type):
                logger.error(f"❌ Invalid alert type: {alert_type}")
                return False
            
            # Merge with default config
            default_config = await self._get_default_config(alert_type)
            final_config = {**default_config, **(config or {})}
            
            query = """
                INSERT INTO alert_subscriptions (symbol, alert_type, enabled, priority, config)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol, alert_type) 
                DO UPDATE SET 
                    enabled = TRUE,
                    priority = EXCLUDED.priority,
                    config = EXCLUDED.config,
                    updated_at = NOW()
                RETURNING id
            """
            
            params = [symbol, alert_type, True, priority, json.dumps(final_config)]
            result = db.execute_update(query, params)
            
            if result > 0:
                # Clear cache
                self._clear_cache()
                logger.info(f"✅ Subscribed {symbol} to {alert_type} alerts")
                return True
            else:
                logger.error(f"❌ Failed to subscribe {symbol} to {alert_type}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error subscribing {symbol} to {alert_type}: {e}")
            return False
    
    async def unsubscribe_symbol(self, symbol: str, alert_type: str) -> bool:
        """Unsubscribe a symbol from an alert type"""
        try:
            query = """
                UPDATE alert_subscriptions 
                SET enabled = FALSE, updated_at = NOW()
                WHERE symbol = %s AND alert_type = %s
                RETURNING id
            """
            
            params = [symbol, alert_type]
            result = db.execute_update(query, params)
            
            if result > 0:
                # Clear cache
                self._clear_cache()
                logger.info(f"🔕 Unsubscribed {symbol} from {alert_type} alerts")
                return True
            else:
                logger.warning(f"⚠️ No active subscription found for {symbol} to {alert_type}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error unsubscribing {symbol} from {alert_type}: {e}")
            return False
    
    async def bulk_subscribe(self, symbols: List[str], alert_types: List[str], 
                            priority: int = 2, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Bulk subscribe multiple symbols to multiple alert types"""
        results = {
            'success': [],
            'failed': [],
            'total': len(symbols) * len(alert_types)
        }
        
        for symbol in symbols:
            for alert_type in alert_types:
                success = await self.subscribe_symbol(symbol, alert_type, priority, config)
                if success:
                    results['success'].append(f"{symbol}:{alert_type}")
                else:
                    results['failed'].append(f"{symbol}:{alert_type}")
        
        logger.info(f"📊 Bulk subscription complete: {len(results['success'])}/{results['total']} successful")
        return results
    
    async def get_alert_types(self) -> List[AlertType]:
        """Get all available alert types"""
        try:
            query = """
                SELECT alert_type, name, description, default_config, is_active, created_at
                FROM alert_types 
                WHERE is_active = TRUE
                ORDER BY name ASC
            """
            
            rows = db.execute_query(query)
            
            alert_types = []
            for row in rows:
                default_config = row[3] or {}
                if isinstance(default_config, str):
                    default_config = json.loads(default_config)
                
                alert_type = AlertType(
                    alert_type=row[0],
                    name=row[1],
                    description=row[2],
                    default_config=default_config,
                    is_active=row[4],
                    created_at=row[5]
                )
                alert_types.append(alert_type)
            
            return alert_types
            
        except Exception as e:
            logger.error(f"❌ Error loading alert types: {e}")
            return []
    
    async def get_subscription_summary(self) -> Dict[str, Any]:
        """Get subscription summary statistics"""
        try:
            # Get counts by alert type
            query = """
                SELECT 
                    alert_type,
                    COUNT(*) as total_subscriptions,
                    COUNT(*) FILTER (WHERE enabled = TRUE) as active_subscriptions
                FROM alert_subscriptions
                GROUP BY alert_type
                ORDER BY active_subscriptions DESC
            """
            
            rows = db.execute_query(query)
            
            summary = {
                'by_alert_type': [],
                'total_symbols': 0,
                'total_active_subscriptions': 0
            }
            
            for row in rows:
                summary['by_alert_type'].append({
                    'alert_type': row[0],
                    'total': row[1],
                    'active': row[2]
                })
                summary['total_active_subscriptions'] += row[2]
            
            # Get unique symbol count
            symbol_query = "SELECT COUNT(DISTINCT symbol) FROM alert_subscriptions WHERE enabled = TRUE"
            symbol_count = db.execute_query(symbol_query)
            summary['total_symbols'] = symbol_count[0][0] if symbol_count else 0
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Error getting subscription summary: {e}")
            return {}
    
    async def _is_valid_alert_type(self, alert_type: str) -> bool:
        """Check if alert type is valid and active"""
        try:
            query = "SELECT 1 FROM alert_types WHERE alert_type = $1 AND is_active = TRUE"
            result = db.execute_query_positional(query, [alert_type])
            return len(result) > 0
        except Exception:
            return False
    
    async def _get_default_config(self, alert_type: str) -> Dict[str, Any]:
        """Get default configuration for an alert type"""
        try:
            query = "SELECT default_config FROM alert_types WHERE alert_type = $1"
            result = db.execute_query_positional(query, [alert_type])
            
            if result and result[0]:
                config = result[0][0] or {}
                if isinstance(config, str):
                    config = json.loads(config)
                return config
            return {}
        except Exception:
            return {}
    
    def _clear_cache(self):
        """Clear subscription cache"""
        self._subscription_cache.clear()
        self._cache_updated.clear()
        logger.debug("🗑️ Subscription cache cleared")


# Global service instance
alert_subscription_service = AlertSubscriptionService()
