#!/usr/bin/env python3
"""
Test Stock Symbol API
"""
import uvicorn
from fastapi import FastAPI
from app.api.stock_symbols import router

# Create FastAPI app
app = FastAPI(
    title="Stock Symbol API",
    description="API for fetching stock symbol details",
    version="1.0.0"
)

# Include stock symbols router
app.include_router(router)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Stock Symbol API",
        "endpoints": {
            "symbol_details": "/api/v1/stocks/symbols/{symbol}/details",
            "health": "/api/v1/stocks/health"
        }
    }

if __name__ == "__main__":
    print("🚀 Starting Stock Symbol API Server...")
    print("📊 Available endpoints:")
    print("   GET http://localhost:8000/api/v1/stocks/symbols/AAPL/details")
    print("   GET http://localhost:8000/api/v1/stocks/health")
    print("   GET http://localhost:8000/")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
