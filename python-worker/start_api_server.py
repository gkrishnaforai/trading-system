#!/usr/bin/env python3
"""
Trading System Python Worker - API Server
Starts the FastAPI server for REST API endpoints
"""
import uvicorn
import os
from app.api_app import app

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("PYTHON_API_HOST", "0.0.0.0")
    port = int(os.getenv("PYTHON_API_PORT", "8001"))
    
    print(f"🚀 Starting Trading System Python Worker API")
    print(f"📍 Server: http://{host}:{port}")
    print(f"📖 API Docs: http://{host}:{port}/docs")
    print(f"🔧 Admin API: http://{host}:{port}/admin")
    
    # Start the FastAPI server
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,  # Set to True for development
        log_level="info"
    )
