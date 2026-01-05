#!/usr/bin/env python3
"""
Simple migration runner for trading signals table
Fixed version that handles database connections properly
"""

import sys
import os
from pathlib import Path

# Add the python-worker directory to the path
sys.path.insert(0, str(Path(__file__).parent))

def create_trading_signals_table():
    """Create the trading_signals table with proper schema"""
    
    try:
        from app.database import db, init_database
        from app.observability.logging import get_logger
        
        logger = get_logger(__name__)
        
        # Initialize database
        init_database()
        logger.info("✅ Database initialized")
        
        # Create table
        create_table_query = """
        CREATE TABLE IF NOT EXISTS trading_signals (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            signal_date DATE NOT NULL,
            signal_type VARCHAR(20) NOT NULL,
            confidence DECIMAL(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            strategy VARCHAR(50) NOT NULL,
            strategy_version VARCHAR(20) DEFAULT '1.0',
            
            -- Price information
            price_at_signal DECIMAL(12,4),
            volume_at_signal BIGINT,
            
            -- Technical indicators
            sma_50 DECIMAL(12,4),
            sma_200 DECIMAL(12,4),
            ema_20 DECIMAL(12,4),
            rsi_14 DECIMAL(8,4),
            macd DECIMAL(8,4),
            macd_signal DECIMAL(8,4),
            
            -- Signal metadata
            signal_strength VARCHAR(20),
            time_horizon VARCHAR(20),
            risk_level VARCHAR(20),
            market_regime VARCHAR(20),
            volatility DECIMAL(8,4),
            
            -- Reasoning
            signal_reason TEXT,
            key_factors JSONB,
            
            -- Performance tracking
            entry_price DECIMAL(12,4),
            exit_price DECIMAL(12,4),
            profit_loss DECIMAL(12,4),
            profit_loss_pct DECIMAL(8,4),
            max_profit DECIMAL(12,4),
            max_loss DECIMAL(12,4),
            holding_days INTEGER,
            
            -- Execution details
            status VARCHAR(20) DEFAULT 'generated',
            executed_at TIMESTAMP,
            closed_at TIMESTAMP,
            
            -- System fields
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            batch_id UUID,
            
            UNIQUE(symbol, signal_date, strategy, created_at)
        );
        """
        
        db.execute_update(create_table_query)
        logger.info("✅ trading_signals table created")
        
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol_date ON trading_signals(symbol, signal_date DESC);",
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_strategy ON trading_signals(strategy);",
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_created_at ON trading_signals(created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_trading_signals_signal_type ON trading_signals(signal_type);"
        ]
        
        for index_sql in indexes:
            db.execute_update(index_sql)
        
        logger.info("✅ Indexes created")
        
        # Test the table
        test_query = "SELECT COUNT(*) as count FROM trading_signals;"
        result = db.execute_query(test_query)
        count = result[0]['count'] if result else 0
        
        logger.info(f"📊 Table verified - current row count: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Creating trading_signals table...")
    
    success = create_trading_signals_table()
    
    if success:
        print("✅ Migration completed successfully!")
        print("\n📊 Table is ready for signal storage")
        print("🔍 Verify with: SELECT COUNT(*) FROM trading_signals;")
    else:
        print("❌ Migration failed")
        sys.exit(1)
