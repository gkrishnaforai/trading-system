"""
Repository for stocks master data and missing symbols management.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date
import pandas as pd
from app.database import db

class StocksRepository:
    """Repository for stocks master data."""
    
    @staticmethod
    def create_table():
        """Create stocks table if it doesn't exist."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS stocks (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL UNIQUE,
            company_name VARCHAR(255),
            exchange VARCHAR(50),
            sector VARCHAR(100),
            industry VARCHAR(100),
            market_cap BIGINT,
            country VARCHAR(100),
            currency VARCHAR(10) DEFAULT 'USD',
            is_active BOOLEAN DEFAULT TRUE,
            listing_date DATE,
            delisting_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            -- Data completeness flags
            has_fundamentals BOOLEAN DEFAULT FALSE,
            has_earnings BOOLEAN DEFAULT FALSE,
            has_market_data BOOLEAN DEFAULT FALSE,
            has_indicators BOOLEAN DEFAULT FALSE,
            
            -- Last data update timestamps
            last_fundamentals_update TIMESTAMP,
            last_earnings_update TIMESTAMP,
            last_market_data_update TIMESTAMP,
            last_indicators_update TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
        CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);
        CREATE INDEX IF NOT EXISTS idx_stocks_exchange ON stocks(exchange);
        CREATE INDEX IF NOT EXISTS idx_stocks_active ON stocks(is_active);
        """
        
        db.execute_update(create_sql)
    
    @staticmethod
    def symbol_exists(symbol: str) -> bool:
        """Check if a symbol exists in the stocks table."""
        query = "SELECT 1 FROM stocks WHERE symbol = %s LIMIT 1"
        result = db.execute_query(query, (symbol.upper(),))
        return len(result) > 0
    
    @staticmethod
    def get_stock(symbol: str) -> Optional[Dict[str, Any]]:
        """Get stock information by symbol."""
        query = "SELECT * FROM stocks WHERE symbol = %s"
        result = db.execute_query(query, (symbol.upper(),))
        return result[0] if result else None
    
    @staticmethod
    def upsert_stock(stock_data: Dict[str, Any]) -> int:
        """Insert or update stock data."""
        if not stock_data or 'symbol' not in stock_data:
            return 0
        
        # Ensure symbol is uppercase
        stock_data['symbol'] = stock_data['symbol'].upper()
        
        # Check if stock exists
        existing = StocksRepository.get_stock(stock_data['symbol'])
        
        if existing:
            # Update existing stock
            update_fields = []
            values = []
            
            for key, value in stock_data.items():
                if key != 'id' and key != 'created_at':
                    update_fields.append(f"{key} = %s")
                    values.append(value)
            
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(stock_data['symbol'])
            
            query = f"""
            UPDATE stocks 
            SET {', '.join(update_fields)}
            WHERE symbol = %s
            """
            
            db.execute_update(query, values)
            return 1
        else:
            # Insert new stock
            columns = list(stock_data.keys())
            placeholders = ', '.join(['%s'] * len(columns))
            
            query = f"""
            INSERT INTO stocks ({', '.join(columns)})
            VALUES ({placeholders})
            """
            
            values = list(stock_data.values())
            db.execute_update(query, values)
            return 1
    
    @staticmethod
    def get_stocks_with_missing_data(data_type: str) -> List[Dict[str, Any]]:
        """Get stocks that are missing specific type of data."""
        query = f"""
        SELECT * FROM stocks 
        WHERE is_active = TRUE 
        AND has_{data_type} = FALSE
        ORDER BY market_cap DESC NULLS LAST
        LIMIT 100
        """
        return db.execute_query(query)

class MissingSymbolsRepository:
    """Repository for managing missing symbols queue."""
    
    @staticmethod
    def create_table():
        """Create missing_symbols_queue table if it doesn't exist."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS missing_symbols_queue (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            source_table VARCHAR(50) NOT NULL,
            source_record_id INTEGER,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'pending',
            error_message TEXT,
            attempts INTEGER DEFAULT 0,
            last_attempt_at TIMESTAMP,
            completed_at TIMESTAMP,
            
            UNIQUE(symbol, source_table, source_record_id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_missing_symbols_status ON missing_symbols_queue(status);
        CREATE INDEX IF NOT EXISTS idx_missing_symbols_discovered ON missing_symbols_queue(discovered_at);
        """
        
        db.execute_update(create_sql)
    
    @staticmethod
    def add_missing_symbol(symbol: str, source_table: str, source_record_id: int = None) -> int:
        """Add a missing symbol to the queue."""
        try:
            query = """
            INSERT INTO missing_symbols_queue (symbol, source_table, source_record_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (symbol, source_table, source_record_id) DO NOTHING
            """
            
            db.execute_update(query, (symbol.upper(), source_table, source_record_id))
            return 1
        except Exception as e:
            print(f"Error adding missing symbol {symbol}: {e}")
            return 0
    
    @staticmethod
    def get_pending_symbols(limit: int = 50) -> List[Dict[str, Any]]:
        """Get pending symbols from the queue."""
        query = """
        SELECT * FROM missing_symbols_queue 
        WHERE status = 'pending' 
        ORDER BY discovered_at ASC
        LIMIT %s
        """
        return db.execute_query(query, (limit,))
    
    @staticmethod
    def update_status(id: int, status: str, error_message: str = None) -> int:
        """Update the status of a missing symbol record."""
        query = """
        UPDATE missing_symbols_queue 
        SET status = %s, 
            error_message = %s,
            last_attempt_at = CURRENT_TIMESTAMP,
            attempts = attempts + 1,
            completed_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END
        WHERE id = %s
        """
        
        db.execute_update(query, (status, error_message, status, id))
        return 1
    
    @staticmethod
    def mark_completed(id: int) -> int:
        """Mark a missing symbol as completed."""
        return MissingSymbolsRepository.update_status(id, 'completed')
    
    @staticmethod
    def mark_failed(id: int, error_message: str) -> int:
        """Mark a missing symbol as failed."""
        return MissingSymbolsRepository.update_status(id, 'failed', error_message)
