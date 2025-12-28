"""
Plugin Registration Manager
DRY & SOLID: Centralized plugin registration with dependency resolution and validation
"""
import logging
from typing import Dict, Any, Optional, List, Type
from pathlib import Path

from app.plugins.base import Plugin, PluginType, PluginMetadata
from app.plugins.base_adapter import PluginInitializationError, PluginAvailabilityError
from app.plugins.data_source_adapters import create_data_source_adapters
from app.plugins.registry import get_registry
from app.observability.logging import get_logger


class PluginRegistrationManager:
    """
    SOLID: Single responsibility for plugin registration and lifecycle management
    DRY: Centralized registration logic with error handling
    """
    
    def __init__(self):
        self._logger = get_logger("plugin.registration")
        self._registry = get_registry()
        self._registered_plugins: Dict[str, Plugin] = {}
    
    def register_all_data_sources(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
        """
        DRY: Register all data source plugins with centralized error handling
        SOLID: Single responsibility for data source registration
        
        Returns:
            Dict mapping plugin names to registration success status
        """
        results = {}
        adapters = create_data_source_adapters()
        
        for adapter in adapters:
            try:
                metadata = adapter.get_metadata()
                plugin_name = metadata.name
                
                self._logger.info(f"Registering data source plugin: {plugin_name}")
                
                # Validate dependencies before registration
                if not self._validate_dependencies(metadata):
                    results[plugin_name] = False
                    continue
                
                # Get plugin-specific config
                plugin_config = config.get(plugin_name, {}) if config else {}
                
                # Register with auto-initialization
                success = self._registry.register(
                    type(adapter),
                    config=plugin_config,
                    auto_initialize=True
                )
                
                if success:
                    self._registered_plugins[plugin_name] = adapter
                    self._logger.info(f"✅ Successfully registered plugin: {plugin_name}")
                else:
                    self._logger.error(f"❌ Failed to register plugin: {plugin_name}")
                
                results[plugin_name] = success
                
            except Exception as e:
                plugin_name = getattr(adapter, '_plugin_name', 'unknown')
                self._logger.error(f"❌ Exception registering plugin {plugin_name}: {str(e)}", exc_info=True)
                results[plugin_name] = False
        
        return results
    
    def register_plugin(self, plugin_class: Type[Plugin], config: Optional[Dict[str, Any]] = None) -> bool:
        """
        SOLID: Register a single plugin with full validation
        DRY: Centralized registration logic
        
        Args:
            plugin_class: Plugin class to register
            config: Plugin configuration
            
        Returns:
            True if registration successful
        """
        try:
            # Create temporary instance to get metadata
            temp_instance = plugin_class()
            metadata = temp_instance.get_metadata()
            plugin_name = metadata.name
            
            self._logger.info(f"Registering plugin: {plugin_name}")
            
            # Validate dependencies
            if not self._validate_dependencies(metadata):
                return False
            
            # Register with auto-initialization
            success = self._registry.register(plugin_class, config, auto_initialize=True)
            
            if success:
                self._registered_plugins[plugin_name] = temp_instance
                self._logger.info(f"✅ Successfully registered plugin: {plugin_name}")
            else:
                self._logger.error(f"❌ Failed to register plugin: {plugin_name}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"❌ Exception registering plugin: {str(e)}", exc_info=True)
            return False
    
    def unregister_plugin(self, plugin_name: str) -> bool:
        """
        SOLID: Unregister plugin with proper cleanup
        Best Practices: Always cleanup resources
        """
        try:
            self._logger.info(f"Unregistering plugin: {plugin_name}")
            
            # Cleanup plugin if it's in our registry
            if plugin_name in self._registered_plugins:
                plugin = self._registered_plugins[plugin_name]
                try:
                    plugin.cleanup()
                except Exception as e:
                    self._logger.warning(f"Error during cleanup of {plugin_name}: {str(e)}")
                del self._registered_plugins[plugin_name]
            
            # Unregister from global registry
            success = self._registry.unregister(plugin_name)
            
            if success:
                self._logger.info(f"✅ Successfully unregistered plugin: {plugin_name}")
            else:
                self._logger.error(f"❌ Failed to unregister plugin: {plugin_name}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"❌ Exception unregistering plugin {plugin_name}: {str(e)}", exc_info=True)
            return False
    
    def _validate_dependencies(self, metadata: PluginMetadata) -> bool:
        """
        DRY: Centralized dependency validation
        SOLID: Single responsibility for dependency checking
        
        Returns:
            True if all dependencies are available
        """
        if not metadata.dependencies:
            return True
        
        missing_deps = []
        for dep in metadata.dependencies:
            if not self._registry.get(dep):
                missing_deps.append(dep)
        
        if missing_deps:
            self._logger.error(f"Plugin '{metadata.name}' has missing dependencies: {missing_deps}")
            return False
        
        return True
    
    def get_plugin_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Best Practices: Health monitoring for all registered plugins
        """
        try:
            return self._registry.health_check()
        except Exception as e:
            self._logger.error(f"Error checking plugin health: {str(e)}", exc_info=True)
            return {}
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """
        Best Practices: Hot reloading for plugins
        """
        try:
            self._logger.info(f"Reloading plugin: {plugin_name}")
            success = self._registry.reload(plugin_name)
            
            if success:
                self._logger.info(f"✅ Successfully reloaded plugin: {plugin_name}")
            else:
                self._logger.error(f"❌ Failed to reload plugin: {plugin_name}")
            
            return success
            
        except Exception as e:
            self._logger.error(f"❌ Exception reloading plugin {plugin_name}: {str(e)}", exc_info=True)
            return False
    
    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> List[str]:
        """
        DRY: Centralized plugin listing
        """
        try:
            return self._registry.list_plugins(plugin_type)
        except Exception as e:
            self._logger.error(f"Error listing plugins: {str(e)}", exc_info=True)
            return []
    
    def shutdown_all(self) -> None:
        """
        Best Practices: Graceful shutdown of all plugins
        """
        self._logger.info("Shutting down all plugins...")
        
        # Cleanup all registered plugins
        for plugin_name in list(self._registered_plugins.keys()):
            try:
                self.unregister_plugin(plugin_name)
            except Exception as e:
                self._logger.error(f"Error during shutdown of {plugin_name}: {str(e)}")
        
        self._logger.info("✅ All plugins shut down")


# Global registration manager instance
_registration_manager: Optional[PluginRegistrationManager] = None


def get_registration_manager() -> PluginRegistrationManager:
    """
    DRY: Singleton pattern for registration manager
    SOLID: Single point of access for plugin registration
    """
    global _registration_manager
    if _registration_manager is None:
        _registration_manager = PluginRegistrationManager()
    return _registration_manager


def initialize_data_sources(config: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
    """
    DRY: Convenience function for initializing all data sources
    SOLID: Single responsibility for data source initialization
    
    Args:
        config: Configuration dictionary with plugin-specific settings
        
    Returns:
        Dict mapping plugin names to initialization success status
    """
    manager = get_registration_manager()
    return manager.register_all_data_sources(config)
