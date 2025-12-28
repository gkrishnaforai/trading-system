"""
Stock Comparison Service
Compares multiple stocks side-by-side
Industry Standard: Stock comparison tool
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.database_helper import DatabaseQueryHelper


class StockComparisonService(BaseService):
    """
    Service for comparing multiple stocks
    
    SOLID: Single Responsibility - only handles stock comparison
    """
    
    def __init__(self):
        """Initialize stock comparison service"""
        super().__init__()
    
    def compare_stocks(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Compare multiple stocks side-by-side
        
        Args:
            symbols: List of stock symbols to compare
        
        Returns:
            Dictionary with comparison data for each stock
        """
        if not symbols:
            raise ValidationError("At least one symbol is required for comparison")
        
        if len(symbols) > 10:
            raise ValidationError("Maximum 10 symbols can be compared at once")
        
        try:
            comparison_data = {}
            
            for symbol in symbols:
                stock_data = self._get_stock_comparison_data(symbol)
                if stock_data:
                    comparison_data[symbol] = stock_data
            
            return {
                "symbols": symbols,
                "comparison": comparison_data,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            self.log_error("Error comparing stocks", e, context={'symbols': symbols})
            raise DatabaseError(f"Failed to compare stocks: {str(e)}", details={'symbols': symbols}) from e
    
    def _get_stock_comparison_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get comparison data for a single stock"""
        try:
            # Build comparison data
            data = {
                "symbol": symbol
            }
            
            # Get latest price (try live_prices first, then raw_market_data)
            price_query = """
                SELECT price, change, change_percent, timestamp
                FROM live_prices
                WHERE stock_symbol = :symbol
                ORDER BY timestamp DESC
                LIMIT 1
            """
            price_result = db.execute_query(price_query, {"symbol": symbol})
            
            if not price_result:
                # Fallback to raw_market_data
                price_query = """
                    SELECT close as price, date
                    FROM raw_market_data
                    WHERE stock_symbol = :symbol
                    ORDER BY date DESC
                    LIMIT 1
                """
                price_result = db.execute_query(price_query, {"symbol": symbol})
            
            if price_result:
                price_data = price_result[0]
                data.update({
                    "current_price": price_data.get('price'),
                    "price_change": price_data.get('change'),
                    "price_change_percent": price_data.get('change_percent')
                })
            
            # Get latest indicators using helper
            indicators_data = DatabaseQueryHelper.get_latest_indicators(symbol)
            
            if indicators_data:
                data.update({
                    "sma50": indicators_data.get('sma50'),
                    "sma200": indicators_data.get('sma200'),
                    "ema20": indicators_data.get('ema20'),
                    "ema50": indicators_data.get('ema50'),
                    "rsi": indicators_data.get('rsi'),
                    "macd": indicators_data.get('macd'),
                    "long_term_trend": indicators_data.get('long_term_trend'),
                    "medium_term_trend": indicators_data.get('medium_term_trend'),
                    "signal": indicators_data.get('signal'),
                    "momentum_score": indicators_data.get('momentum_score')
                })
            
            # Get fundamentals using helper
            fundamentals = DatabaseQueryHelper.get_fundamentals(symbol)
            if fundamentals:
                data.update({
                    "pe_ratio": fundamentals.get('pe_ratio'),
                    "market_cap": fundamentals.get('market_cap'),
                    "dividend_yield": fundamentals.get('dividend_yield'),
                    "eps": fundamentals.get('eps'),
                    "revenue": fundamentals.get('revenue')
                })
            
            # Get sector/industry (try holdings first, then watchlist_items)
            sector_query = """
                SELECT sector, industry
                FROM holdings
                WHERE stock_symbol = :symbol AND sector IS NOT NULL
                LIMIT 1
            """
            sector_result = db.execute_query(sector_query, {"symbol": symbol})
            
            if not sector_result:
                sector_query = """
                    SELECT sector, industry
                    FROM watchlist_items
                    WHERE stock_symbol = :symbol AND sector IS NOT NULL
                    LIMIT 1
                """
                sector_result = db.execute_query(sector_query, {"symbol": symbol})
            
            if sector_result:
                sector_data = sector_result[0]
                data.update({
                    "sector": sector_data.get('sector'),
                    "industry": sector_data.get('industry')
                })
            
            # Return data if we have at least price, indicators, or fundamentals
            # Even if minimal, return the symbol data
            if data.get('current_price') is not None or data.get('sma50') is not None or data.get('pe_ratio') is not None:
                return data
            
            # If we have at least the symbol, return it (for cases where data hasn't been loaded yet)
            if data.get('symbol'):
                return data
            
            return None
            
        except Exception as e:
            logger.warning(f"Error getting comparison data for {symbol}: {e}")
            return None

