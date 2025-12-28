"""
Plugin Loader
Automatically loads and registers plugins from configuration
Industry Standard: Configuration-Driven Plugin Loading
"""
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List

from app.plugins import get_registry
from app.plugins.base import Plugin

logger = logging.getLogger(__name__)


def load_plugins_from_config(config_path: Path) -> int:
    """
    Load plugins from YAML configuration file
    
    Args:
        config_path: Path to plugins configuration file
    
    Returns:
        Number of plugins loaded
    """
    if not config_path.exists():
        logger.warning(f"Plugin config file not found: {config_path}")
        return 0
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        registry = get_registry()
        count = 0
        
        # Load data sources
        if 'data_sources' in config:
            count += _load_plugin_list(config['data_sources'], registry)
        
        # Load strategies
        if 'strategies' in config:
            count += _load_plugin_list(config['strategies'], registry)
        
        # Load agents
        if 'agents' in config:
            count += _load_plugin_list(config['agents'], registry)
        
        # Load indicators
        if 'indicators' in config:
            count += _load_plugin_list(config['indicators'], registry)
        
        # Load workflows
        if 'workflows' in config:
            count += _load_plugin_list(config['workflows'], registry)
        
        logger.info(f"✅ Loaded {count} plugins from {config_path}")
        return count
        
    except Exception as e:
        logger.error(f"Error loading plugins from config: {e}", exc_info=True)
        return 0


def _load_plugin_list(plugin_list: List[Dict[str, Any]], registry) -> int:
    """Load a list of plugins"""
    count = 0
    for plugin_config in plugin_list:
        try:
            module_path = plugin_config.get('module')
            class_name = plugin_config.get('class')
            config = plugin_config.get('config', {})
            
            if not module_path or not class_name:
                logger.warning(f"Invalid plugin config: {plugin_config}")
                continue
            
            # Import module and get class
            module = __import__(module_path, fromlist=[class_name])
            plugin_class = getattr(module, class_name)
            
            # Register plugin
            if registry.register(plugin_class, config):
                count += 1
                
        except Exception as e:
            logger.error(f"Error loading plugin {plugin_config}: {e}", exc_info=True)
    
    return count


def auto_discover_plugins(plugin_dir: Path) -> int:
    """
    Auto-discover plugins from a directory
    
    Args:
        plugin_dir: Directory containing plugin modules
    
    Returns:
        Number of plugins discovered
    """
    if not plugin_dir.exists():
        logger.warning(f"Plugin directory not found: {plugin_dir}")
        return 0
    
    registry = get_registry()
    count = 0
    
    # Look for Python files in plugin directory
    for file_path in plugin_dir.glob("*.py"):
        if file_path.name.startswith("_"):
            continue
        
        try:
            # Try to load plugins from this module
            module_name = f"{plugin_dir.name}.{file_path.stem}"
            if registry.load_from_module(module_name):
                count += 1
        except Exception as e:
            logger.debug(f"Error loading from {file_path}: {e}")
    
    logger.info(f"✅ Auto-discovered {count} plugins from {plugin_dir}")
    return count

