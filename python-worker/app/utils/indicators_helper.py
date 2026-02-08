# Helper functions for accessing indicators stored as separate rows

def get_all_indicators_for_date(symbol: str, date: str) -> dict:
    """
    Get all indicators for a symbol on a specific date
    
    Args:
        symbol: Stock symbol
        date: Date string (YYYY-MM-DD)
    
    Returns:
        Dictionary with indicator names as keys and values as values
    """
    from app.database import db
    from sqlalchemy import text
    
    query = """
        SELECT indicator_name, indicator_value 
        FROM indicators_daily 
        WHERE symbol = :symbol AND date = :date
    """
    
    try:
        result = db.execute_query(query, {"symbol": symbol, "date": date})
        indicators = {}
        for row in result:
            indicators[row['indicator_name']] = row['indicator_value']
        return indicators
    except Exception as e:
        print(f"Error fetching indicators: {e}")
        return {}

def get_latest_indicators(symbol: str) -> dict:
    """
    Get the latest indicators for a symbol
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Dictionary with indicator names as keys and values as values
    """
    from app.database import db
    from sqlalchemy import text
    
    query = """
        SELECT indicator_name, indicator_value, date
        FROM indicators_daily 
        WHERE symbol = :symbol 
        ORDER BY date DESC
    """
    
    try:
        result = db.execute_query(query, {"symbol": symbol})
        indicators = {}
        latest_date = None
        
        for row in result:
            if latest_date is None:
                latest_date = row['date']
            if row['date'] == latest_date:
                indicators[row['indicator_name']] = row['indicator_value']
        
        return indicators
    except Exception as e:
        print(f"Error fetching latest indicators: {e}")
        return {}

def get_indicator_history(symbol: str, indicator_name: str, limit: int = 30) -> list:
    """
    Get historical values for a specific indicator
    
    Args:
        symbol: Stock symbol
        indicator_name: Name of the indicator (e.g., 'sma_50', 'rsi_14')
        limit: Maximum number of records to return
    
    Returns:
        List of dictionaries with date and value
    """
    from app.database import db
    from sqlalchemy import text
    
    query = """
        SELECT date, indicator_value
        FROM indicators_daily 
        WHERE symbol = :symbol AND indicator_name = :indicator_name
        ORDER BY date DESC
        LIMIT :limit
    """
    
    try:
        result = db.execute_query(query, {
            "symbol": symbol, 
            "indicator_name": indicator_name, 
            "limit": limit
        })
        return [{"date": row['date'], "value": row['indicator_value']} for row in result]
    except Exception as e:
        print(f"Error fetching indicator history: {e}")
        return []

# Example usage:
if __name__ == "__main__":
    # Get all indicators for AAPL today
    indicators = get_all_indicators_for_date("AAPL", "2025-01-20")
    print(f"AAPL indicators: {indicators}")
    
    # Get latest indicators for MSFT
    latest = get_latest_indicators("MSFT")
    print(f"MSFT latest indicators: {latest}")
    
    # Get RSI history for AAPL
    rsi_history = get_indicator_history("AAPL", "rsi_14", 10)
    print(f"AAPL RSI history: {rsi_history}")
