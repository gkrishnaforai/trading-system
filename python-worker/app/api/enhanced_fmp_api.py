"""
Enhanced FMP API Endpoints
Exposes all the new FMP data types through REST API
"""
from fastapi import APIRouter, HTTPException, Query, Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.services.optimized_fmp_loader import optimized_fmp_loader
from app.observability.logging import get_logger

logger = get_logger("enhanced_fmp_api")

router = APIRouter(tags=["market-data"])


# Response Models
class RealTimePriceResponse(BaseModel):
    symbol: str
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    timestamp: str


class CompanyProfileResponse(BaseModel):
    symbol: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[int] = None
    website: Optional[str] = None


class FinancialStatementResponse(BaseModel):
    symbol: str
    period: str
    data: List[Dict[str, Any]]
    fetched_at: str


class KeyMetricsResponse(BaseModel):
    symbol: str
    period: str
    metrics: List[Dict[str, Any]]
    fetched_at: str


class AnalystDataResponse(BaseModel):
    symbol: str
    ratings: List[Dict[str, Any]]
    price_targets: List[Dict[str, Any]]
    grades: List[Dict[str, Any]]
    fetched_at: str


class MarketNewsResponse(BaseModel):
    articles: List[Dict[str, Any]]
    total_count: int
    fetched_at: str


class ComprehensiveDataResponse(BaseModel):
    symbol: str
    real_time_price: Optional[Dict[str, Any]] = None
    company_profile: Optional[Dict[str, Any]] = None
    financials: Optional[Dict[str, Any]] = None
    analyst_data: Optional[Dict[str, Any]] = None
    market_news: Optional[List[Dict[str, Any]]] = None
    errors: List[str] = []
    fetched_at: str


# === REAL-TIME DATA ===

@router.get("/price/{symbol}", response_model=RealTimePriceResponse)
async def get_real_time_price(symbol: str = Path(..., description="Stock symbol")):
    """Get real-time stock price"""
    try:
        price_data = optimized_fmp_loader.get_real_time_price(symbol)
        
        if not price_data:
            raise HTTPException(status_code=404, detail=f"Price data not found for {symbol}")
        
        return RealTimePriceResponse(
            symbol=symbol,
            price=price_data.get("price", 0.0),
            change=price_data.get("change"),
            change_percent=price_data.get("changesPercent"),
            timestamp=price_data.get("timestamp", "")
        )
        
    except Exception as e:
        logger.error(f"Error fetching real-time price for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prices/batch", response_model=List[RealTimePriceResponse])
async def get_batch_prices(symbols: str = Query(..., description="Comma-separated stock symbols")):
    """Get real-time prices for multiple symbols"""
    try:
        symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        results = []
        
        for symbol in symbol_list:
            price_data = optimized_fmp_loader.get_real_time_price(symbol)
            if price_data:
                results.append(RealTimePriceResponse(
                    symbol=symbol,
                    price=price_data.get("price", 0.0),
                    change=price_data.get("change"),
                    change_percent=price_data.get("changesPercent"),
                    timestamp=price_data.get("timestamp", "")
                ))
        
        return results
        
    except Exception as e:
        logger.error(f"Error fetching batch prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === COMPANY INFORMATION ===

@router.get("/profile/{symbol}", response_model=CompanyProfileResponse)
async def get_company_profile(symbol: str = Path(..., description="Stock symbol")):
    """Get company profile"""
    try:
        profile = optimized_fmp_loader.get_company_profile(symbol)
        
        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile not found for {symbol}")
        
        return CompanyProfileResponse(
            symbol=symbol,
            company_name=profile.get("companyName", ""),
            sector=profile.get("sector"),
            industry=profile.get("industry"),
            market_cap=profile.get("marketCap"),
            website=profile.get("website")
        )
        
    except Exception as e:
        logger.error(f"Error fetching company profile for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=List[Dict[str, Any]])
async def search_symbols(query: str = Query(..., description="Search query"), limit: int = Query(10, description="Number of results")):
    """Search for company symbols"""
    try:
        results = optimized_fmp_loader.search_symbol(query)
        return results[:limit]
        
    except Exception as e:
        logger.error(f"Error searching symbols for {query}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock-list", response_model=List[Dict[str, Any]])
async def get_stock_list(limit: int = Query(100, description="Number of stocks to return")):
    """Get list of available stocks"""
    try:
        stock_list = optimized_fmp_loader.get_stock_list()
        return stock_list[:limit]
        
    except Exception as e:
        logger.error(f"Error fetching stock list: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === FINANCIAL STATEMENTS ===

@router.get("/financials/income-statement/{symbol}", response_model=FinancialStatementResponse)
async def get_income_statement(
    symbol: str = Path(..., description="Stock symbol"),
    period: str = Query("quarter", description="Period (quarter/annual)")
):
    """Get income statement"""
    try:
        data = optimized_fmp_loader.get_income_statement(symbol, period)
        
        return FinancialStatementResponse(
            symbol=symbol,
            period=period,
            data=data,
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching income statement for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/financials/balance-sheet/{symbol}", response_model=FinancialStatementResponse)
async def get_balance_sheet(
    symbol: str = Path(..., description="Stock symbol"),
    period: str = Query("quarter", description="Period (quarter/annual)")
):
    """Get balance sheet"""
    try:
        data = optimized_fmp_loader.get_balance_sheet(symbol, period)
        
        return FinancialStatementResponse(
            symbol=symbol,
            period=period,
            data=data,
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching balance sheet for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/financials/cash-flow/{symbol}", response_model=FinancialStatementResponse)
async def get_cash_flow(
    symbol: str = Path(..., description="Stock symbol"),
    period: str = Query("quarter", description="Period (quarter/annual)")
):
    """Get cash flow statement"""
    try:
        data = optimized_fmp_loader.get_cash_flow(symbol, period)
        
        return FinancialStatementResponse(
            symbol=symbol,
            period=period,
            data=data,
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching cash flow for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === FINANCIAL METRICS ===

@router.get("/metrics/key-metrics/{symbol}", response_model=KeyMetricsResponse)
async def get_key_metrics(
    symbol: str = Path(..., description="Stock symbol"),
    period: str = Query("quarter", description="Period (quarter/annual)")
):
    """Get key financial metrics"""
    try:
        metrics = optimized_fmp_loader.get_key_metrics(symbol, period)
        
        return KeyMetricsResponse(
            symbol=symbol,
            period=period,
            metrics=metrics,
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching key metrics for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/financial-ratios/{symbol}", response_model=KeyMetricsResponse)
async def get_financial_ratios(
    symbol: str = Path(..., description="Stock symbol"),
    period: str = Query("quarter", description="Period (quarter/annual)")
):
    """Get financial ratios"""
    try:
        ratios = optimized_fmp_loader.get_financial_ratios(symbol, period)
        
        return KeyMetricsResponse(
            symbol=symbol,
            period=period,
            metrics=ratios,
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching financial ratios for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/financial-scores/{symbol}", response_model=KeyMetricsResponse)
async def get_financial_scores(symbol: str = Path(..., description="Stock symbol")):
    """Get financial health scores"""
    try:
        scores = optimized_fmp_loader.get_financial_scores(symbol)
        
        return KeyMetricsResponse(
            symbol=symbol,
            period="ttm",
            metrics=scores,
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching financial scores for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === ANALYST DATA ===
# NOTE: Analyst ratings endpoints moved to stock_grades_api.py for better organization
# This consolidates all grades/ratings functionality under one router


# === MARKET NEWS ===

@router.get("/news/market", response_model=MarketNewsResponse)
async def get_market_news(limit: int = Query(20, description="Number of articles")):
    """Get market news"""
    try:
        news = optimized_fmp_loader.get_market_news(limit)
        
        return MarketNewsResponse(
            articles=news,
            total_count=len(news),
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching market news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === COMPREHENSIVE DATA ===

@router.get("/comprehensive/{symbol}", response_model=ComprehensiveDataResponse)
async def get_comprehensive_data(
    symbol: str = Path(..., description="Stock symbol"),
    include_analyst: bool = Query(True, description="Include analyst data"),
    include_news: bool = Query(False, description="Include market news")
):
    """Get comprehensive data for a symbol"""
    try:
        errors = []
        
        # Get basic data
        real_time_price = optimized_fmp_loader.get_real_time_price(symbol)
        company_profile = optimized_fmp_loader.get_company_profile(symbol)
        financials = optimized_fmp_loader.get_financials(symbol)
        
        # Get optional data
        analyst_data = None
        if include_analyst:
            try:
                ratings = optimized_fmp_loader.get_analyst_ratings(symbol)
                targets = optimized_fmp_loader.get_price_targets(symbol)
                grades = optimized_fmp_loader.get_stock_grades(symbol)
                analyst_data = {
                    "ratings": ratings,
                    "price_targets": targets,
                    "grades": grades
                }
            except Exception as e:
                errors.append(f"Analyst data error: {str(e)}")
        
        market_news = None
        if include_news:
            try:
                market_news = optimized_fmp_loader.get_market_news(limit=10)
            except Exception as e:
                errors.append(f"Market news error: {str(e)}")
        
        return ComprehensiveDataResponse(
            symbol=symbol,
            real_time_price=real_time_price,
            company_profile=company_profile,
            financials=financials,
            analyst_data=analyst_data,
            market_news=market_news,
            errors=errors,
            fetched_at=optimized_fmp_loader._get_current_timestamp()
        )
        
    except Exception as e:
        logger.error(f"Error fetching comprehensive data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === BULK OPERATIONS ===

class BulkLoadRequest(BaseModel):
    symbols: List[str] = Field(..., description="List of stock symbols")
    load_on_demand: bool = Field(False, description="Load on-demand data")

@router.post("/bulk/load", response_model=Dict[str, Any])
async def bulk_load_data(request: BulkLoadRequest):
    """Bulk load data for multiple symbols"""
    try:
        symbols = request.symbols
        load_on_demand = request.load_on_demand
        
        if len(symbols) > 50:  # Limit bulk operations
            raise HTTPException(status_code=400, detail="Too many symbols. Maximum 50 allowed.")
        
        results = optimized_fmp_loader.load_all_data_for_symbols(symbols, load_on_demand=load_on_demand)
        return results
        
    except Exception as e:
        logger.error(f"Error in bulk load: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class OnDemandRequest(BaseModel):
    data_types: List[str] = Field(..., description="List of data types to load")

@router.post("/bulk/on-demand/{symbol}", response_model=Dict[str, Any])
async def get_on_demand_bulk(
    request: OnDemandRequest,
    symbol: str = Path(..., description="Stock symbol")
):
    """Get multiple on-demand data types for a symbol"""
    try:
        result = optimized_fmp_loader.get_on_demand_data(symbol, request.data_types)
        return result
        
    except Exception as e:
        logger.error(f"Error fetching on-demand data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === CACHE MANAGEMENT ===

@router.get("/cache/stats", response_model=Dict[str, Any])
async def get_cache_stats():
    """Get cache statistics"""
    try:
        stats = optimized_fmp_loader.get_cache_stats()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache(pattern: Optional[str] = Query(None, description="Cache pattern to clear")):
    """Clear cache"""
    try:
        optimized_fmp_loader.clear_cache(pattern)
        return {"message": f"Cache cleared for pattern: {pattern or 'all'}"}
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === HEALTH CHECK ===

@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """Health check for FMP API"""
    try:
        # Test basic functionality
        test_symbol = "AAPL"
        price = optimized_fmp_loader.get_real_time_price(test_symbol)
        
        cache_stats = optimized_fmp_loader.get_cache_stats()
        
        return {
            "status": "healthy" if price else "degraded",
            "fmp_client": "connected",
            "cache_size": cache_stats.get("cache_size", 0),
            "test_symbol": test_symbol,
            "price_available": price is not None,
            "timestamp": optimized_fmp_loader._get_current_timestamp()
        }
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": optimized_fmp_loader._get_current_timestamp()
        }


# Helper method for timestamp
def _get_current_timestamp() -> str:
    """Get current timestamp"""
    from datetime import datetime
    return datetime.now().isoformat()


# Add the helper method to the loader class
optimized_fmp_loader._get_current_timestamp = _get_current_timestamp
