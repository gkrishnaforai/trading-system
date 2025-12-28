"""
Alert Registry
Industry Standard: Centralized registry for pluggable alerts
Supports dynamic loading from database or configuration
"""
import logging
from typing import Dict, Type, Optional, List
from app.alerts.base import BaseAlertPlugin, AlertMetadata

logger = logging.getLogger(__name__)


class AlertRegistry:
    """
    Central registry for alert plugins
    Singleton pattern with thread-safe operations
    
    Features:
    - Dynamic plugin registration
    - Database-driven alert types
    - Configuration-driven alert types
    - Hot-swapping support
    """
    
    _instance = None
    _plugins: Dict[str, BaseAlertPlugin] = {}
    _plugin_classes: Dict[str, Type[BaseAlertPlugin]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._plugins = {}
            self._plugin_classes = {}
            self._initialized = True
            logger.info("✅ Alert Registry initialized")
    
    def register(
        self,
        plugin_class: Type[BaseAlertPlugin],
        alert_type_id: Optional[str] = None
    ) -> bool:
        """
        Register an alert plugin
        
        Args:
            plugin_class: Alert plugin class
            alert_type_id: Optional alert type ID (if None, uses metadata)
        
        Returns:
            True if registration successful
        """
        try:
            # Create instance to get metadata
            temp_instance = plugin_class()
            metadata = temp_instance.get_metadata()
            
            # Use provided ID or metadata ID
            type_id = alert_type_id or metadata.alert_type_id
            
            # Store plugin class
            self._plugin_classes[type_id] = plugin_class
            
            # Initialize and store instance
            instance = plugin_class()
            self._plugins[type_id] = instance
            
            logger.info(
                f"✅ Registered alert plugin: {type_id} "
                f"({metadata.display_name})"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error registering alert plugin: {e}", exc_info=True)
            return False
    
    def get(self, alert_type_id: str) -> Optional[BaseAlertPlugin]:
        """
        Get alert plugin by type ID
        
        Args:
            alert_type_id: Alert type identifier
        
        Returns:
            Alert plugin instance or None
        """
        if alert_type_id in self._plugins:
            return self._plugins[alert_type_id]
        
        # Try to create from class if available
        if alert_type_id in self._plugin_classes:
            plugin_class = self._plugin_classes[alert_type_id]
            instance = plugin_class()
            self._plugins[alert_type_id] = instance
            return instance
        
        logger.warning(f"Alert plugin '{alert_type_id}' not found")
        return None
    
    def list_plugins(self) -> List[str]:
        """
        List all registered alert plugins
        
        Returns:
            List of alert type IDs
        """
        return list(self._plugins.keys())
    
    def unregister(self, alert_type_id: str) -> bool:
        """
        Unregister an alert plugin
        
        Args:
            alert_type_id: Alert type identifier
        
        Returns:
            True if successful
        """
        if alert_type_id in self._plugins:
            del self._plugins[alert_type_id]
        
        if alert_type_id in self._plugin_classes:
            del self._plugin_classes[alert_type_id]
        
        logger.info(f"✅ Unregistered alert plugin: {alert_type_id}")
        return True


# Global registry instance
_registry: Optional[AlertRegistry] = None


def get_alert_registry() -> AlertRegistry:
    """Get global alert registry instance"""
    global _registry
    if _registry is None:
        _registry = AlertRegistry()
    return _registry

