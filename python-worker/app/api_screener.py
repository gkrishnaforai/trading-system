"""
Stock Screener API Endpoints
Add these endpoints to your main API server
"""
from fastapi import HTTPException
from typing import Optional
import logging

from app.services.stock_screener_service import StockScreenerService
from app.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Initialize screener service (should be initialized in main API server)
stock_screener_service = StockScreenerService()


def register_screener_endpoints(app):
    """
    Register screener endpoints with FastAPI app
    
    Usage in api_server.py:
        from app.api_screener import register_screener_endpoints
        register_screener_endpoints(app)
    """
    
    @app.get("/api/v1/screener/stocks")
    async def screen_stocks(
        price_below_sma50: Optional[bool] = None,
        price_below_sma200: Optional[bool] = None,
        has_good_fundamentals: Optional[bool] = None,
        is_growth_stock: Optional[bool] = None,
        is_exponential_growth: Optional[bool] = None,
        min_fundamental_score: Optional[float] = None,
        min_rsi: Optional[float] = None,
        max_rsi: Optional[float] = None,
        trend_filter: Optional[str] = None,
        min_market_cap: Optional[float] = None,
        max_pe_ratio: Optional[float] = None,
        limit: int = 100
    ):
        """
        Screen stocks based on criteria
        
        Industry Standard: Similar to Finviz, TradingView, Yahoo Finance screeners
        
        Example: 
        - /api/v1/screener/stocks?price_below_sma50=true&has_good_fundamentals=true&limit=50
        - /api/v1/screener/stocks?price_below_sma200=true&is_growth_stock=true&limit=100
        """
        try:
            results = stock_screener_service.screen_stocks(
                price_below_sma50=price_below_sma50,
                price_below_sma200=price_below_sma200,
                has_good_fundamentals=has_good_fundamentals,
                is_growth_stock=is_growth_stock,
                is_exponential_growth=is_exponential_growth,
                min_fundamental_score=min_fundamental_score,
                min_rsi=min_rsi,
                max_rsi=max_rsi,
                trend_filter=trend_filter,
                min_market_cap=min_market_cap,
                max_pe_ratio=max_pe_ratio,
                limit=limit
            )
            
            # results is already a dict with 'stocks', 'count', 'criteria'
            # Return it directly with success flag
            return {
                "success": True,
                **results  # Unpack: stocks, count, criteria
            }
        except ValidationError as e:
            logger.error(f"Validation error in stock screener: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error screening stocks: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/screener/presets")
    async def get_screener_presets():
        """
        Get predefined screener presets
        
        Returns common screening configurations like:
        - Value stocks below 50-day average
        - Growth stocks below 200-day average
        - Oversold with good fundamentals
        """
        try:
            presets = stock_screener_service.get_screener_presets()
            return {
                "success": True,
                "presets": presets
            }
        except Exception as e:
            logger.error(f"Error getting screener presets: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

