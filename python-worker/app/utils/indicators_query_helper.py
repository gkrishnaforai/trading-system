"""
Helper functions for indicators_daily queries - avoids views, uses pivot queries
Centralizes all indicator access logic for easy maintenance
"""

def get_indicators_wide_query(symbol: str, date: str = None, limit: int = 1) -> str:
    """
    Generate pivot query to get indicators in wide format
    
    Args:
        symbol: Stock symbol
        date: Optional specific date
        limit: Number of records to return
    
    Returns:
        SQL query string
    """
    base_query = """
        SELECT 
            i.symbol,
            i.date,
            MAX(CASE WHEN i.indicator_name = 'sma_50' THEN i.indicator_value END) as sma_50,
            MAX(CASE WHEN i.indicator_name = 'sma_200' THEN i.indicator_value END) as sma_200,
            MAX(CASE WHEN i.indicator_name = 'ema_20' THEN i.indicator_value END) as ema_20,
            MAX(CASE WHEN i.indicator_name = 'rsi_14' THEN i.indicator_value END) as rsi_14,
            MAX(CASE WHEN i.indicator_name = 'macd' THEN i.indicator_value END) as macd,
            MAX(CASE WHEN i.indicator_name = 'macd_signal' THEN i.indicator_value END) as macd_signal,
            MAX(CASE WHEN i.indicator_name = 'macd_hist' THEN i.indicator_value END) as macd_hist,
            MAX(CASE WHEN i.indicator_name = 'atr' THEN i.indicator_value END) as atr,
            MAX(CASE WHEN i.indicator_name = 'bb_width' THEN i.indicator_value END) as bb_width,
            MAX(CASE WHEN i.indicator_name = 'signal' THEN i.indicator_value END) as signal,
            MAX(CASE WHEN i.indicator_name = 'confidence_score' THEN i.indicator_value END) as confidence_score
        FROM indicators_daily i
        WHERE i.symbol = :symbol
    """
    
    if date:
        base_query += " AND i.date = :date"
    
    base_query += " GROUP BY i.symbol, i.date ORDER BY i.date DESC"
    
    if limit:
        base_query += f" LIMIT {limit}"
    
    return base_query

def get_indicators_with_price_query(symbol: str, date: str = None, limit: int = 1) -> str:
    """
    Generate query to get indicators with price data (for APIs)
    
    Args:
        symbol: Stock symbol
        date: Optional specific date
        limit: Number of records to return
    
    Returns:
        SQL query string
    """
    indicators_query = get_indicators_wide_query(symbol, date, limit)
    
    full_query = f"""
        SELECT 
            i.date, r.close, i.rsi_14, i.sma_50, i.ema_20, i.macd, i.macd_signal, 
            r.volume, r.low, r.high, i.atr, i.bb_width, i.signal, i.confidence_score
        FROM ({indicators_query}) i
        JOIN raw_market_data_daily r ON i.symbol = r.symbol AND i.date = r.date
        ORDER BY i.date DESC
    """
    
    return full_query

def get_backtest_indicators_query(symbol: str, backtest_date: str) -> str:
    """
    Generate query for backtesting (indicators as of specific date)
    
    Args:
        symbol: Stock symbol
        backtest_date: Date for backtesting
    
    Returns:
        SQL query string
    """
    return f"""
        SELECT 
            sma_50, sma_200, ema_20, rsi_14, macd, macd_signal, atr, bb_width, signal, confidence_score
        FROM (
            {get_indicators_wide_query(symbol, limit=None)}
        ) indicators_wide
        WHERE date <= :backtest_date 
        ORDER BY date DESC LIMIT 1
    """

# Example usage:
if __name__ == "__main__":
    # Get latest indicators for AAPL
    query = get_indicators_wide_query("AAPL")
    print("Latest indicators query:")
    print(query)
    
    # Get indicators with price for API
    api_query = get_indicators_with_price_query("AAPL")
    print("\nAPI query with price:")
    print(api_query)
    
    # Get backtesting indicators
    backtest_query = get_backtest_indicators_query("AAPL", "2024-01-01")
    print("\nBacktest query:")
    print(backtest_query)
