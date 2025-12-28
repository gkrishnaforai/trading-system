"""
Database Query Helper Utility
DRY: Reduces duplication of common database query patterns
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date

from app.database import db
from app.exceptions import DatabaseError, ValidationError
from app.utils.validation import validate_symbol

logger = logging.getLogger(__name__)


class DatabaseQueryHelper:
    """
    Helper class for common database query patterns
    Reduces code duplication across services
    """
    
    @staticmethod
    def get_stock_by_symbol(symbol: str, table: str = "raw_market_data_daily") -> Optional[Dict[str, Any]]:
        """
        Get latest stock data by symbol
        
        Args:
            symbol: Stock symbol
            table: Table name (default: raw_market_data)
        
        Returns:
            Dictionary with stock data or None if not found
        
        Raises:
            ValidationError: If symbol is invalid
        """
        if not validate_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}", details={'symbol': symbol})
        
        try:
            query = f"""
                SELECT * FROM {table}
                WHERE stock_symbol = :symbol
                ORDER BY trade_date DESC
                LIMIT 1
            """
            result = db.execute_query(query, {"symbol": symbol.upper()})
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to fetch stock data for {symbol}: {str(e)}") from e
    
    @staticmethod
    def get_stock_count(symbol: str, table: str = "raw_market_data_daily") -> int:
        """
        Get count of records for a symbol
        
        Args:
            symbol: Stock symbol
            table: Table name
        
        Returns:
            Count of records
        """
        if not validate_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}", details={'symbol': symbol})
        
        try:
            query = f"""
                SELECT COUNT(*) as count
                FROM {table}
                WHERE stock_symbol = :symbol
            """
            result = db.execute_query(query, {"symbol": symbol.upper()})
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"Error counting records for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to count records for {symbol}: {str(e)}") from e
    
    @staticmethod
    def get_latest_indicators(symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest indicators for a symbol
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Dictionary with latest indicators or None if not found
        """
        if not validate_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}", details={'symbol': symbol})
        
        try:
            query = """
                SELECT * FROM indicators_daily
                WHERE stock_symbol = :symbol
                ORDER BY trade_date DESC
                LIMIT 1
            """
            result = db.execute_query(query, {"symbol": symbol.upper()})
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error fetching indicators for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to fetch indicators for {symbol}: {str(e)}") from e
    
    @staticmethod
    def get_historical_data(
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data for a symbol
        
        Args:
            symbol: Stock symbol
            start_date: Optional start date
            end_date: Optional end date
            limit: Optional limit on number of records
        
        Returns:
            List of dictionaries with historical data
        """
        if not validate_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}", details={'symbol': symbol})
        
        try:
            query = """
                SELECT trade_date as date, open, high, low, close, volume
                FROM raw_market_data_daily
                WHERE stock_symbol = :symbol
            """
            params = {"symbol": symbol.upper()}
            
            if start_date:
                query += " AND trade_date >= :start_date"
                params["start_date"] = start_date.isoformat()
            
            if end_date:
                query += " AND trade_date <= :end_date"
                params["end_date"] = end_date.isoformat()
            
            query += " ORDER BY trade_date ASC"
            
            if limit:
                query += " LIMIT :limit"
                params["limit"] = limit
            
            result = db.execute_query(query, params)
            return result if result else []
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to fetch historical data for {symbol}: {str(e)}") from e
    
    @staticmethod
    def check_data_exists(symbol: str, table: str = "raw_market_data") -> bool:
        """
        Check if data exists for a symbol
        
        Args:
            symbol: Stock symbol
            table: Table name
        
        Returns:
            True if data exists, False otherwise
        """
        try:
            count = DatabaseQueryHelper.get_stock_count(symbol, table)
            return count > 0
        except Exception:
            return False
    
    @staticmethod
    def get_fundamentals(symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get fundamental data for a symbol
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Dictionary with fundamental data or None if not found
        """
        if not validate_symbol(symbol):
            raise ValidationError(f"Invalid symbol: {symbol}", details={'symbol': symbol})
        
        try:
            query = """
                SELECT payload
                FROM fundamentals_snapshots
                WHERE stock_symbol = :symbol
                ORDER BY as_of_date DESC
                LIMIT 1
            """
            result = db.execute_query(query, {"symbol": symbol.upper()})
            if result and result[0].get('payload'):
                return result[0]['payload']
            return None
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}", exc_info=True)
            raise DatabaseError(f"Failed to fetch fundamentals for {symbol}: {str(e)}") from e

