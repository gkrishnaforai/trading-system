"""
Stock Symbol Details API
SOLID: Single responsibility for stock symbol operations
DRY: Centralized symbol data fetching
Performance: Caching, error handling, rate limiting
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from app.observability.logging import get_logger
from app.observability.tracing import trace_function
from app.data_sources.adapters import create_adapter
from app.config import settings


# Pydantic models for API responses
class StockSymbolDetails(BaseModel):
    """Stock symbol details response model"""
    symbol: str = Field(..., description="Stock symbol")
    name: Optional[str] = Field(None, description="Company name")
    description: Optional[str] = Field(None, description="Company description")
    sector: Optional[str] = Field(None, description="Industry sector")
    industry: Optional[str] = Field(None, description="Industry")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    currency: Optional[str] = Field(None, description="Currency")
    country: Optional[str] = Field(None, description="Country")
    exchange: Optional[str] = Field(None, description="Exchange")
    market: Optional[str] = Field(None, description="Market")
    type: Optional[str] = Field(None, description="Security type")
    active: Optional[bool] = Field(None, description="Is actively trading")
    source: str = Field(..., description="Data source")
    last_updated: datetime = Field(..., description="Last update timestamp")


class StockSymbolList(BaseModel):
    """List of stock symbols response"""
    symbols: List[StockSymbolDetails] = Field(..., description="Stock symbols")
    total: int = Field(..., description="Total count")
    source: str = Field(..., description="Data source")


# Router
# ========================================
# IMPORTANT: Router Configuration Rules
# ========================================
# DO NOT ADD PREFIX HERE! Prefixes are managed in api_server.py
# WRONG: router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])
# CORRECT: router = APIRouter(tags=["stocks"])
# ========================================
router = APIRouter(tags=["stocks"])
logger = get_logger("stock_symbols_api")


class StockSymbolService:
    """Service for fetching stock symbol details"""
    
    def __init__(self):
        self._massive_adapter = None
        self._yahoo_adapter = None
        self._fallback_adapter = None
        self._cache = {}  # Simple in-memory cache
        self._cache_ttl = 300  # 5 minutes
    
    def _get_adapters(self):
        """Lazy initialization of adapters"""
        if not self._massive_adapter:
            try:
                self._massive_adapter = create_adapter("massive")
                config = {
                    "api_key": settings.massive_api_key,
                    "rate_limit_calls": settings.massive_rate_limit_calls,
                    "rate_limit_window": settings.massive_rate_limit_window
                }
                self._massive_adapter.initialize(config)
            except Exception as e:
                logger.warning(f"Failed to initialize Massive adapter: {e}")
        
        if not self._yahoo_adapter:
            try:
                self._yahoo_adapter = create_adapter("yahoo_finance")
                self._yahoo_adapter.initialize({"timeout": 30})
            except Exception as e:
                logger.warning(f"Failed to initialize Yahoo adapter: {e}")
        
        if not self._fallback_adapter:
            try:
                self._fallback_adapter = create_adapter("fallback")
                self._fallback_adapter.initialize({"cache_enabled": True})
            except Exception as e:
                logger.warning(f"Failed to initialize Fallback adapter: {e}")
    
    def _get_from_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """Get data from cache"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now().timestamp() - timestamp < self._cache_ttl:
                return data
            else:
                del self._cache[key]
        return None
    
    def _set_cache(self, key: str, data: Dict[str, Any]):
        """Set data in cache"""
        self._cache[key] = (data, datetime.now().timestamp())
    
    @trace_function("get_symbol_details_massive")
    def _get_symbol_details_massive(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol details from Massive.com API"""
        if not self._massive_adapter or not self._massive_adapter.is_available():
            return None
        
        try:
            # Use the Massive.com API endpoint directly
            import requests
            
            url = f"https://api.massive.com/v3/reference/tickers/{symbol.upper()}"
            params = {"apiKey": settings.massive_api_key}
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if "results" in data and data["results"]:
                ticker_data = data["results"]
                
                return {
                    "symbol": ticker_data.get("ticker", symbol),
                    "name": ticker_data.get("name"),
                    "description": ticker_data.get("description"),
                    "sector": ticker_data.get("sector"),
                    "industry": ticker_data.get("industry"),
                    "market_cap": ticker_data.get("market_cap"),
                    "currency": ticker_data.get("currency_name"),
                    "country": ticker_data.get("country_name"),
                    "exchange": ticker_data.get("primary_exchange"),
                    "market": ticker_data.get("market"),
                    "type": ticker_data.get("type"),
                    "active": ticker_data.get("active", True),
                    "source": "massive"
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching from Massive API: {e}")
            return None
    
    @trace_function("get_symbol_details_yahoo")
    def _get_symbol_details_yahoo(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol details from Yahoo Finance"""
        if not self._yahoo_adapter or not self._yahoo_adapter.is_available():
            return None
        
        try:
            # Use yfinance for detailed info
            import yfinance as yf
            
            ticker = yf.Ticker(symbol.upper())
            info = ticker.info
            
            return {
                "symbol": symbol.upper(),
                "name": info.get("longName") or info.get("shortName"),
                "description": info.get("longBusinessSummary"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "currency": info.get("currency"),
                "country": info.get("country"),
                "exchange": info.get("exchange"),
                "market": info.get("market"),
                "type": "Equity",
                "active": True,
                "source": "yahoo"
            }
            
        except Exception as e:
            logger.error(f"Error fetching from Yahoo Finance: {e}")
            return None
    
    @trace_function("get_symbol_details")
    def get_symbol_details(self, symbol: str) -> StockSymbolDetails:
        """Get stock symbol details with fallback"""
        symbol = symbol.upper()
        
        # Check cache first
        cache_key = f"symbol_details_{symbol}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data:
            return StockSymbolDetails(**cached_data)
        
        # Initialize adapters
        self._get_adapters()
        
        # Try Massive first (most comprehensive)
        details = self._get_symbol_details_massive(symbol)
        
        # Fallback to Yahoo Finance
        if not details:
            details = self._get_symbol_details_yahoo(symbol)
        
        # Final fallback
        if not details:
            details = {
                "symbol": symbol,
                "name": None,
                "description": None,
                "sector": None,
                "industry": None,
                "market_cap": None,
                "currency": None,
                "country": None,
                "exchange": None,
                "market": None,
                "type": None,
                "active": None,
                "source": "none"
            }
        
        # Cache the result
        self._set_cache(cache_key, details)
        
        return StockSymbolDetails(**details)


# Service instance
service = StockSymbolService()


@router.get("/symbols/{symbol}/details", response_model=StockSymbolDetails)
async def get_symbol_details(
    symbol: str = Path(..., description="Stock symbol (e.g., AAPL, MSFT, GOOGL)")
):
    """
    Get detailed information for a stock symbol
    
    Args:
        symbol: Stock symbol to lookup
        
    Returns:
        Detailed stock symbol information
        
    Examples:
        - GET /api/v1/stocks/symbols/AAPL/details
        - GET /api/v1/stocks/symbols/MSFT/details
    """
    try:
        details = service.get_symbol_details(symbol)
        
        if details.source == "none":
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{symbol}' not found or no data available"
            )
        
        return details
        
    except Exception as e:
        logger.error(f"Error getting symbol details for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{symbol}", response_model=StockSymbolDetails)
async def get_symbol(symbol: str = Path(..., description="Stock symbol")):
    """Alias for symbol details endpoint"""
    return await get_symbol_details(symbol)


@router.post("/symbols/batch", response_model=StockSymbolList)
async def get_batch_symbol_details(
    symbols: List[str] = Query(..., description="List of stock symbols")
):
    """
    Get details for multiple stock symbols
    
    Args:
        symbols: List of stock symbols to lookup
        
    Returns:
        List of stock symbol details
        
    Examples:
        - POST /api/v1/stocks/symbols/batch?symbols=AAPL&symbols=MSFT&symbols=GOOGL
    """
    try:
        results = []
        
        for symbol in symbols:
            try:
                details = service.get_symbol_details(symbol)
                if details.source != "none":
                    results.append(details)
            except Exception as e:
                logger.warning(f"Failed to get details for {symbol}: {e}")
                continue
        
        return StockSymbolList(
            symbols=results,
            total=len(results),
            source="batch"
        )
        
    except Exception as e:
        logger.error(f"Error in batch symbol lookup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check for stock symbols API"""
    service._get_adapters()
    
    status = {
        "massive_available": service._massive_adapter and service._massive_adapter.is_available(),
        "yahoo_available": service._yahoo_adapter and service._yahoo_adapter.is_available(),
        "fallback_available": service._fallback_adapter and service._fallback_adapter.is_available(),
        "cache_size": len(service._cache)
    }
    
    return status
