"""
FastAPI Application for Trading System Python Worker
Provides REST API endpoints for data management, signals, and admin operations
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.database import init_database
from app.observability.logging import get_logger
from app.api import admin, main
from app.plugins import initialize_data_sources

logger = get_logger("fastapi_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("🚀 Starting FastAPI application...")
    
    # Initialize database
    try:
        init_database()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise
    
    # Initialize plugins
    try:
        # Prepare plugin configuration from settings (same as main.py)
        from app.config import settings
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
        
        plugin_results = initialize_data_sources(plugin_config)
        successful = sum(1 for success in plugin_results.values() if success)
        total = len(plugin_results)
        logger.info(f"✅ Plugins initialized: {successful}/{total}")
    except Exception as e:
        logger.error(f"❌ Failed to initialize plugins: {e}")
        # Don't raise - allow app to start with limited functionality
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down FastAPI application...")


# Create FastAPI application
app = FastAPI(
    title="Trading System Python Worker API",
    description="REST API for data management, signals, and administrative operations",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin.router)
app.include_router(main.router)

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Trading System Python Worker API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        from app.database import db
        db.execute_query("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" else "unhealthy",
        "database": db_status,
        "timestamp": "2025-01-26T14:30:00Z"
    }


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTP exception: {exc.status_code} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "type": "http_error",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "type": "internal_error",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
