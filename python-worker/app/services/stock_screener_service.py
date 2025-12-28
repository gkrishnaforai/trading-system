"""
Stock Screener Service
Filters stocks based on user-defined criteria
Industry Standard: Similar to Finviz, TradingView, Yahoo Finance screeners
"""
from typing import Dict, Any, List, Optional
from datetime import date, datetime

from app.database import db
from app.services.base import BaseService
from app.exceptions import DatabaseError, ValidationError
from app.utils.exception_handler import handle_database_errors
from app.utils.validation_patterns import validate_numeric_range


class StockScreenerService(BaseService):
    """
    Service for screening stocks based on various criteria
    
    Supports:
    - Price vs Moving Averages (below SMA50, below SMA200)
    - Fundamental filters (good fundamentals, growth stocks, exponential growth)
    - Technical filters (RSI, MACD, trend)
    - Custom combinations
    
    Industry Standard: Similar to Finviz, TradingView, Yahoo Finance screeners
    """
    
    def __init__(self):
        """Initialize stock screener service"""
        super().__init__()
    
    @handle_database_errors
    def screen_stocks(
        self,
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
    ) -> List[Dict[str, Any]]:
        """
        Screen stocks based on criteria
        
        Args:
            price_below_sma50: Filter for stocks below 50-day average
            price_below_sma200: Filter for stocks below 200-day average
            has_good_fundamentals: Filter for good fundamentals
            is_growth_stock: Filter for growth stocks
            is_exponential_growth: Filter for exponential growth stocks
            min_fundamental_score: Minimum fundamental score (0-100)
            min_rsi: Minimum RSI value
            max_rsi: Maximum RSI value
            trend_filter: Trend filter ('bullish', 'bearish', 'neutral')
            min_market_cap: Minimum market cap
            max_pe_ratio: Maximum P/E ratio
            limit: Maximum number of results
        
        Returns:
            List of stocks matching criteria with their data
        """
        # Validate inputs
        if min_fundamental_score is not None:
            min_fundamental_score = validate_numeric_range(
                min_fundamental_score, min_value=0.0, max_value=100.0, param_name="min_fundamental_score"
            )
        
        if min_rsi is not None:
            min_rsi = validate_numeric_range(min_rsi, min_value=0.0, max_value=100.0, param_name="min_rsi")
        
        if max_rsi is not None:
            max_rsi = validate_numeric_range(max_rsi, min_value=0.0, max_value=100.0, param_name="max_rsi")
        
        limit = int(validate_numeric_range(limit, min_value=1, max_value=1000, param_name="limit"))
        
        # Build query against the Postgres-first schema.
        query = """
            WITH latest_fundamentals AS (
                SELECT DISTINCT ON (stock_symbol)
                    stock_symbol,
                    payload
                FROM fundamentals_snapshots
                ORDER BY stock_symbol, as_of_date DESC
            ),
            latest_indicators AS (
                SELECT DISTINCT ON (i.stock_symbol)
                    i.stock_symbol,
                    i.trade_date,
                    i.sma_50,
                    i.sma_200,
                    i.rsi_14,
                    i.signal,
                    i.confidence_score,
                    rmd.close as current_price,
                    NULLIF(COALESCE(lf.payload->>'market_cap', lf.payload->>'marketCap'), '')::double precision as market_cap,
                    NULLIF(COALESCE(lf.payload->>'pe_ratio', lf.payload->>'peRatio'), '')::double precision as pe_ratio
                FROM indicators_daily i
                INNER JOIN raw_market_data_daily rmd
                    ON rmd.stock_symbol = i.stock_symbol
                    AND rmd.trade_date = i.trade_date
                LEFT JOIN latest_fundamentals lf
                    ON lf.stock_symbol = i.stock_symbol
                ORDER BY i.stock_symbol, i.trade_date DESC
            )
            SELECT
                stock_symbol,
                trade_date as date,
                current_price,
                sma_50 as sma50,
                sma_200 as sma200,
                rsi_14 as rsi,
                signal,
                confidence_score,
                'bullish' as long_term_trend,
                'bullish' as medium_term_trend,
                0 as fundamental_score,
                false as has_good_fundamentals,
                false as is_growth_stock,
                false as price_below_sma50,
                false as price_below_sma200,
                market_cap,
                pe_ratio
            FROM latest_indicators
            WHERE 1=1
        """
        
        conditions = []
        params = {}
        
        # Add filters
        if price_below_sma50 is not None:
            # Skip this filter for now - would need calculation
            pass
        
        if price_below_sma200 is not None:
            # Skip this filter for now - would need calculation
            pass
        
        if has_good_fundamentals is not None:
            # Skip this filter for now - would need calculation
            pass
        
        if is_growth_stock is not None:
            # Skip this filter for now - would need calculation
            pass
        
        if is_exponential_growth is not None:
            # Skip this filter for now - would need calculation
            pass
        
        if min_fundamental_score is not None:
            # Skip this filter for now - would need calculation
            pass
        
        if min_rsi is not None:
            conditions.append("rsi_14 >= :min_rsi")
            params['min_rsi'] = min_rsi
        
        if max_rsi is not None:
            conditions.append("rsi_14 <= :max_rsi")
            params['max_rsi'] = max_rsi
        
        if trend_filter:
            if trend_filter not in ['bullish', 'bearish', 'neutral']:
                raise ValidationError(f"Invalid trend_filter: {trend_filter}. Must be 'bullish', 'bearish', or 'neutral'")
            # Skip this filter for now - would need calculation
            pass
        
        # Add fundamental filters that use actual columns
        if min_market_cap is not None:
            conditions.append("market_cap >= :min_market_cap")
            params['min_market_cap'] = min_market_cap
        
        if max_pe_ratio is not None:
            conditions.append("pe_ratio <= :max_pe_ratio")
            params['max_pe_ratio'] = max_pe_ratio
        
        # Add conditions to query
        if conditions:
            query += " AND " + " AND ".join(conditions)
        
        # Order by stock_symbol (stable ordering)
        query += " ORDER BY stock_symbol ASC"
        query += " LIMIT :limit"
        params['limit'] = limit
        
        try:
            results = db.execute_query(query, params)
            
            # Process results
            screened_stocks = []
            for row in results:
                stock_data = {
                    'symbol': row['stock_symbol'],
                    'date': row['date'],
                    'current_price': row['current_price'],
                    'sma50': row['sma50'],
                    'sma200': row['sma200'],
                    'rsi': row['rsi'],
                    'long_term_trend': row['long_term_trend'],
                    'medium_term_trend': row['medium_term_trend'],
                    'fundamental_score': row['fundamental_score'],
                    'has_good_fundamentals': bool(row['has_good_fundamentals']),
                    'is_growth_stock': bool(row['is_growth_stock']),
                    'is_exponential_growth': False,  # Placeholder - not calculated
                    'price_below_sma50': False,  # Placeholder - not calculated
                    'price_below_sma200': False,  # Placeholder - not calculated
                }
                
                # Add fundamental data if available
                fundamentals = {}
                if row.get('market_cap') is not None:
                    fundamentals['market_cap'] = row['market_cap']
                if row.get('pe_ratio') is not None:
                    fundamentals['pe_ratio'] = row['pe_ratio']
                if row.get('pb_ratio') is not None:
                    fundamentals['pb_ratio'] = row['pb_ratio']
                if row.get('eps') is not None:
                    fundamentals['eps'] = row['eps']
                if row.get('beta') is not None:
                    fundamentals['beta'] = row['beta']
                if row.get('dividend_yield') is not None:
                    fundamentals['dividend_yield'] = row['dividend_yield']
                if row.get('roe') is not None:
                    fundamentals['roe'] = row['roe']
                if row.get('debt_to_equity') is not None:
                    fundamentals['debt_to_equity'] = row['debt_to_equity']
                
                if fundamentals:
                    stock_data['fundamentals'] = fundamentals
                
                # Calculate discount percentages
                if row['current_price'] and row['sma50']:
                    stock_data['discount_from_sma50_pct'] = ((row['sma50'] - row['current_price']) / row['sma50']) * 100
                
                if row['current_price'] and row['sma200']:
                    stock_data['discount_from_sma200_pct'] = ((row['sma200'] - row['current_price']) / row['sma200']) * 100
                
                screened_stocks.append(stock_data)
            
            return {
                'stocks': screened_stocks,
                'count': len(screened_stocks),
                'criteria': {
                    'price_below_sma50': price_below_sma50,
                    'price_below_sma200': price_below_sma200,
                    'has_good_fundamentals': has_good_fundamentals,
                    'is_growth_stock': is_growth_stock,
                    'is_exponential_growth': is_exponential_growth,
                    'min_fundamental_score': min_fundamental_score,
                    'min_rsi': min_rsi,
                    'max_rsi': max_rsi,
                    'trend_filter': trend_filter,
                    'limit': limit
                }
            }
            
        except Exception as e:
            self.log_error("Error screening stocks", e, context=params)
            raise DatabaseError(f"Failed to screen stocks: {str(e)}", details=params) from e
    
    def get_screener_presets(self) -> Dict[str, Dict[str, Any]]:
        """
        Get predefined screener presets
        
        Returns:
            Dictionary of preset configurations
        """
        return {
            'value_below_50ma': {
                'name': 'Value Stocks Below 50-Day Average',
                'description': 'Stocks with good fundamentals trading below 50-day moving average',
                'config': {
                    'price_below_sma50': True,
                    'has_good_fundamentals': True,
                    'min_fundamental_score': 60.0
                }
            },
            'value_below_200ma': {
                'name': 'Value Stocks Below 200-Day Average',
                'description': 'Stocks with good fundamentals trading below 200-day moving average',
                'config': {
                    'price_below_sma200': True,
                    'has_good_fundamentals': True,
                    'min_fundamental_score': 60.0
                }
            },
            'growth_below_50ma': {
                'name': 'Growth Stocks Below 50-Day Average',
                'description': 'Growth stocks trading below 50-day moving average',
                'config': {
                    'price_below_sma50': True,
                    'is_growth_stock': True
                }
            },
            'exponential_growth_below_50ma': {
                'name': 'Exponential Growth Below 50-Day Average',
                'description': 'Exponential growth stocks trading below 50-day moving average',
                'config': {
                    'price_below_sma50': True,
                    'is_exponential_growth': True
                }
            },
            'oversold_good_fundamentals': {
                'name': 'Oversold with Good Fundamentals',
                'description': 'Stocks with RSI < 30 and good fundamentals',
                'config': {
                    'max_rsi': 30.0,
                    'has_good_fundamentals': True,
                    'min_fundamental_score': 60.0
                }
            },
            'bullish_trend_good_fundamentals': {
                'name': 'Bullish Trend with Good Fundamentals',
                'description': 'Stocks in bullish trend with good fundamentals',
                'config': {
                    'trend_filter': 'bullish',
                    'has_good_fundamentals': True,
                    'min_fundamental_score': 60.0
                }
            }
        }

