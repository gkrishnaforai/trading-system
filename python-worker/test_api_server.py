#!/usr/bin/env python3
"""
Trading System Python Worker - API Server (Test Mode)
Starts the FastAPI server for REST API endpoints without database dependency
"""
import uvicorn
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Create a minimal FastAPI app for testing
app = FastAPI(
    title="Trading System Python Worker API - Test Mode",
    description="REST API for data management, signals, and administrative operations (Test Mode)",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Trading System Python Worker API - Test Mode",
        "version": "1.0.0",
        "status": "running",
        "note": "Database not connected - test mode only"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database": "disconnected",
        "timestamp": "2025-01-26T14:30:00Z",
        "mode": "test"
    }

@app.get("/admin/data-sources")
async def get_data_sources():
    """Get data sources (test data)"""
    return {
        "data_sources": [
            {
                "name": "massive",
                "status": "active",
                "last_sync": "2 mins ago",
                "data_types": ["price_historical", "fundamentals", "news", "earnings"],
                "api_calls_today": 1247,
                "error_rate": 0.1,
                "config": {"rate_limit": 60, "enabled": True}
            },
            {
                "name": "alphavantage",
                "status": "inactive",
                "last_sync": "N/A",
                "data_types": ["price_historical", "technical"],
                "api_calls_today": 0,
                "error_rate": 0.0,
                "config": {"rate_limit": 5, "enabled": False, "error": "API key required"}
            },
            {
                "name": "yahoo_finance",
                "status": "active",
                "last_sync": "5 mins ago",
                "data_types": ["price_historical"],
                "api_calls_today": 89,
                "error_rate": 0.0,
                "config": {"rate_limit": 100, "enabled": True}
            }
        ]
    }

@app.get("/admin/health")
async def get_system_health():
    """Get system health (test data)"""
    return {
        "status": "healthy",
        "timestamp": "2025-01-26T14:35:00Z",
        "services": {
            "database": {"status": "disconnected", "response_time": 9999},
            "python_api": {"status": "healthy", "response_time": 45},
            "data_sources": {
                "massive": {"status": "healthy", "last_sync": "2 mins ago"},
                "alphavantage": {"status": "inactive", "last_sync": "N/A"},
                "yahoo": {"status": "healthy", "last_sync": "5 mins ago"}
            }
        },
        "metrics": {
            "cpu_usage": 45.2,
            "memory_usage": 67.8,
            "disk_usage": 72.1,
            "active_connections": 23
        }
    }

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("PYTHON_API_HOST", "0.0.0.0")
    port = int(os.getenv("PYTHON_API_PORT", "8002"))
    
    print(f"🚀 Starting Trading System Python Worker API (Test Mode)")
    print(f"📍 Server: http://{host}:{port}")
    print(f"📖 API Docs: http://{host}:{port}/docs")
    print(f"🔧 Admin API: http://{host}:{port}/admin")
    print(f"⚠️  Note: Database not connected - test mode only")
    
    # Start the FastAPI server
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
