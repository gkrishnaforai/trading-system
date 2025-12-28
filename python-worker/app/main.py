"""
Python AI/ML Worker - Main Entry Point
DRY & SOLID: Centralized plugin initialization with best practices
Handles LLM narrative generation, indicators, and analysis
"""
import logging
import os
from typing import Dict, Any

from app.config import settings
from app.observability.logging import setup_logging, get_logger, log_config
from app.database import init_database
from app.observability.metrics import get_metrics
from app.workers.batch_worker import BatchWorker
from app.plugins import initialize_data_sources, get_registration_manager

# Setup structured logging
setup_logging()
logger = get_logger(__name__)
metrics = get_metrics()


def initialize_plugins() -> Dict[str, bool]:
    """
    SOLID: Single responsibility for plugin initialization
    DRY: Centralized plugin setup with error handling
    Best Practices: Graceful failure handling and reporting
    
    Returns:
        Dict mapping plugin names to initialization success status
    """
    logger.info("🔌 Initializing data source plugins...")
    
    try:
        # Prepare plugin configuration from settings
        plugin_config = {
            "massive": {
                "api_key": settings.massive_api_key,
                "rate_limit_calls": getattr(settings, 'massive_rate_limit_calls', 4),
                "rate_limit_window": getattr(settings, 'massive_rate_limit_window', 60.0)
            },
            "alphavantage": {
                "api_key": settings.alphavantage_api_key,
                "rate_limit_calls": getattr(settings, 'alphavantage_rate_limit_calls', 1),
                "rate_limit_window": getattr(settings, 'alphavantage_rate_limit_window', 1.0),
                "timeout": getattr(settings, 'alphavantage_timeout', 30)
            },
            "yahoo_finance": {
                "timeout": getattr(settings, 'yahoo_finance_timeout', 30),
                "retry_count": getattr(settings, 'yahoo_finance_retry_count', 3)
            },
            "fallback": {
                "cache_enabled": getattr(settings, 'fallback_cache_enabled', True),
                "cache_ttl": getattr(settings, 'fallback_cache_ttl', 3600)
            }
        }
        
        # Initialize all data source plugins
        results = initialize_data_sources(plugin_config)
        
        # Report results
        successful = [name for name, success in results.items() if success]
        failed = [name for name, success in results.items() if not success]
        
        if successful:
            logger.info(f"✅ Successfully initialized plugins: {', '.join(successful)}")
        
        if failed:
            logger.error(f"❌ Failed to initialize plugins: {', '.join(failed)}")
        
        # Log plugin health
        registration_manager = get_registration_manager()
        health = registration_manager.get_plugin_health()
        
        for plugin_name, status in health.items():
            if status.get('healthy', False):
                logger.info(f"🟢 Plugin '{plugin_name}' is healthy (v{status.get('version', 'unknown')})")
            else:
                logger.warning(f"🔴 Plugin '{plugin_name}' is unhealthy: {status.get('error', 'Unknown error')}")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Critical error during plugin initialization: {str(e)}", exc_info=True)
        return {}


def cleanup_plugins() -> None:
    """
    Best Practices: Graceful plugin cleanup on shutdown
    """
    logger.info("🧹 Cleaning up plugins...")
    
    try:
        registration_manager = get_registration_manager()
        registration_manager.shutdown_all()
        logger.info("✅ All plugins cleaned up successfully")
        
    except Exception as e:
        logger.error(f"Error during plugin cleanup: {str(e)}", exc_info=True)


def main():
    """Main worker entry point with plugin support"""
    logger.info("🚀 Starting Trading System Python AI/ML Worker...")
    
    # Log configuration (with masked secrets)
    log_config()
    
    # Initialize database
    init_database()
    
    # Initialize plugins with best practices
    plugin_results = initialize_plugins()
    
    # Check if critical plugins are available
    critical_plugins = ['massive'] if settings.massive_enabled else ['yahoo_finance']
    missing_critical = [p for p in critical_plugins if not plugin_results.get(p, False)]
    
    if missing_critical:
        logger.warning(f"⚠️ Critical plugins not available: {', '.join(missing_critical)}")
        logger.info("System will continue with limited functionality")
    
    try:
        # Start batch worker scheduler
        logger.info("📋 Starting batch worker scheduler...")
        worker = BatchWorker()
        worker.start_scheduler()
        
        logger.info("✅ Trading System Python AI/ML Worker started successfully")
        
        # Keep the main thread alive
        import signal
        import time
        
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            cleanup_plugins()
            worker.stop()
            exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Main loop
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}", exc_info=True)
        
    finally:
        # Always cleanup on exit
        cleanup_plugins()
        logger.info("👋 Trading System Python AI/ML Worker stopped")


if __name__ == "__main__":
    main()
