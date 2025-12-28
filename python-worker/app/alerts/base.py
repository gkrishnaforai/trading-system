"""
Base Alert Plugin Interface
Industry Standard: Plugin pattern for extensible alert system
Allows adding new alert types without code changes
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class NotificationChannel(Enum):
    """Notification channels"""
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"


@dataclass
class AlertMetadata:
    """Metadata for an alert plugin"""
    alert_type_id: str
    name: str
    display_name: str
    description: str
    version: str
    config_schema: Dict[str, Any]
    supported_channels: List[NotificationChannel]
    subscription_level_required: str  # 'basic', 'pro', 'elite'


@dataclass
class AlertContext:
    """Context data for alert evaluation"""
    user_id: str
    portfolio_id: Optional[str] = None
    stock_symbol: Optional[str] = None
    current_price: Optional[float] = None
    indicators: Optional[Dict[str, Any]] = None
    signal: Optional[str] = None
    volume: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class AlertResult:
    """Result of alert evaluation"""
    triggered: bool
    message: str
    severity: AlertSeverity
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class BaseAlertPlugin(ABC):
    """
    Base class for all alert plugins
    Industry Standard: Plugin pattern with clear contract
    
    New alert types can be added by:
    1. Creating a class that extends BaseAlertPlugin
    2. Registering it in the alert registry
    3. Adding entry to alert_types table (or via config)
    
    No code changes needed in core system!
    """
    
    @abstractmethod
    def get_metadata(self) -> AlertMetadata:
        """
        Get alert plugin metadata
        
        Returns:
            AlertMetadata with plugin information
        """
        pass
    
    @abstractmethod
    def evaluate(
        self,
        context: AlertContext,
        config: Dict[str, Any]
    ) -> AlertResult:
        """
        Evaluate alert condition
        
        Args:
            context: Alert context (price, indicators, signal, etc.)
            config: Alert configuration (thresholds, conditions, etc.)
        
        Returns:
            AlertResult indicating if alert should trigger
        """
        pass
    
    @abstractmethod
    def send_notification(
        self,
        result: AlertResult,
        context: AlertContext,
        channel: NotificationChannel,
        recipient: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send alert notification via specified channel
        
        Args:
            result: Alert result with message and severity
            context: Alert context
            channel: Notification channel (email, sms, etc.)
            recipient: Recipient address (email, phone, etc.)
            config: Channel-specific configuration
        
        Returns:
            True if notification sent successfully
        
        Raises:
            AlertNotificationError: If notification fails
        """
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate alert configuration
        
        Args:
            config: Alert configuration to validate
        
        Returns:
            True if configuration is valid
        
        Raises:
            ValidationError: If configuration is invalid
        """
        pass
    
    def is_available(self) -> bool:
        """
        Check if alert plugin is available/healthy
        
        Returns:
            True if plugin is available
        """
        return True

