#!/usr/bin/env python3
"""
Simple Stock Symbol API Server
Exposes Massive.com API endpoints with proper error handling
"""
import json
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.config import settings

# Pydantic model for response
class StockSymbol(BaseModel):
    symbol: str
    name: Optional[str]
    market: Optional[str]
    exchange: Optional[str]
    market_cap: Optional[float]
    currency: Optional[str]
    country: Optional[str]
    type: Optional[str]
    active: Optional[bool]
    employees: Optional[int]
    phone: Optional[str]
    website: Optional[str]
    address: Optional[str]
    description: Optional[str]
    source: str = "massive"
    last_updated: datetime

# Create FastAPI app
app = FastAPI(
    title="Stock Symbol API",
    description="Simple API for stock symbol details using Massive.com",
    version="1.0.0"
)

def get_symbol_details(symbol: str) -> dict:
    """Get symbol details from Massive.com API"""
    url = f"https://api.massive.com/v3/reference/tickers/{symbol.upper()}"
    params = {"apiKey": settings.massive_api_key}
    
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    
    if "results" not in data or not data["results"]:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
    
    ticker = data["results"]
    address = ticker.get('address', {})
    
    return {
        "symbol": ticker.get('ticker', symbol),
        "name": ticker.get('name'),
        "market": ticker.get('market'),
        "exchange": ticker.get('primary_exchange'),
        "market_cap": ticker.get('market_cap'),
        "currency": ticker.get('currency_name'),
        "country": ticker.get('locale', '').upper(),
        "type": ticker.get('type'),
        "active": ticker.get('active'),
        "employees": ticker.get('total_employees'),
        "phone": ticker.get('phone_number'),
        "website": ticker.get('homepage_url'),
        "address": f"{address.get('address1', '')}, {address.get('city', '')}, {address.get('state', '')} {address.get('postal_code', '')}".strip(", ") if address else None,
        "description": ticker.get('description'),
        "source": "massive",
        "last_updated": datetime.now()
    }

@app.get("/")
async def root():
    return {
        "message": "Stock Symbol API",
        "version": "1.0.0",
        "endpoints": {
            "symbol_details": "/stocks/{symbol}",
            "health": "/health"
        }
    }

@app.get("/stocks/{symbol}", response_model=StockSymbol)
async def get_stock(symbol: str):
    """Get stock symbol details"""
    try:
        details = get_symbol_details(symbol)
        return StockSymbol(**details)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid API key or plan limitation")
        elif e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
        else:
            raise HTTPException(status_code=500, detail=f"API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Health check"""
    try:
        # Test API with a simple request
        test_response = requests.get(
            f"https://api.massive.com/v3/reference/tickers/AAPL",
            params={"apiKey": settings.massive_api_key},
            timeout=10
        )
        
        return {
            "status": "healthy",
            "massive_api": "connected" if test_response.status_code == 200 else "disconnected",
            "api_key_configured": bool(settings.massive_api_key)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "massive_api": "disconnected",
            "api_key_configured": bool(settings.massive_api_key)
        }

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Starting Simple Stock API Server...")
    print("📊 Available endpoints:")
    print("   GET http://localhost:8000/stocks/AAPL")
    print("   GET http://localhost:8000/stocks/MSFT")
    print("   GET http://localhost:8000/health")
    print("   GET http://localhost:8000/")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
