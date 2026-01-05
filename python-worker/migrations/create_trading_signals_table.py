#!/usr/bin/env python3
"""
Migration script to create the trading_signals table
Following industry standards for signal storage and analysis
"""

import sys
import os
from pathlib import Path

# Add the python-worker directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import db, init_database
from app.observability.logging import get_logger

logger = get_logger(__name__)

def create_trading_signals_table():
    """Create the trading_signals table with proper schema and indexes"""
    
    create_table_query = """
    CREATE TABLE IF NOT EXISTS trading_signals (
        -- Primary identification
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        signal_date DATE NOT NULL,
        signal_type VARCHAR(20) NOT NULL CHECK (signal_type IN ('buy', 'sell', 'hold', 'neutral', 'long', 'short')),
        confidence DECIMAL(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        strategy VARCHAR(50) NOT NULL,
        strategy_version VARCHAR(20) DEFAULT '1.0',
        
        -- Price information at signal time
        price_at_signal DECIMAL(12,4),
        volume_at_signal BIGINT,
        
        -- Technical indicators that influenced the signal
        sma_50 DECIMAL(12,4),
        sma_200 DECIMAL(12,4),
        ema_20 DECIMAL(12,4),
        rsi_14 DECIMAL(8,4),
        macd DECIMAL(8,4),
        macd_signal DECIMAL(8,4),
        
        -- Signal metadata
        signal_strength VARCHAR(20) CHECK (signal_strength IN ('weak', 'moderate', 'strong')),
        time_horizon VARCHAR(20) CHECK (time_horizon IN ('intraday', 'short_term', 'medium_term', 'long_term')),
        risk_level VARCHAR(20) CHECK (risk_level IN ('low', 'medium', 'high')),
        
        -- Market context
        market_regime VARCHAR(20) CHECK (market_regime IN ('bull', 'bear', 'sideways', 'volatile')),
        volatility DECIMAL(8,4),
        
        -- Reasoning and explanation
        signal_reason TEXT,
        key_factors JSONB,
        
        -- Performance tracking fields
        entry_price DECIMAL(12,4),
        exit_price DECIMAL(12,4),
        profit_loss DECIMAL(12,4),
        profit_loss_pct DECIMAL(8,4),
        max_profit DECIMAL(12,4),
        max_loss DECIMAL(12,4),
        holding_days INTEGER,
        
        -- Execution details
        status VARCHAR(20) DEFAULT 'generated' CHECK (status IN ('generated', 'executed', 'closed', 'cancelled', 'expired')),
        executed_at TIMESTAMP,
        closed_at TIMESTAMP,
        
        -- System fields
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        batch_id UUID,
        
        -- Constraints
        UNIQUE(symbol, signal_date, strategy, created_at)
    );
    """
    
    # Create performance tracking indexes
    performance_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol_date ON trading_signals(symbol, signal_date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_strategy ON trading_signals(strategy);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_signal_type ON trading_signals(signal_type);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_confidence ON trading_signals(confidence DESC);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_created_at ON trading_signals(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_status ON trading_signals(status);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_signal_date ON trading_signals(signal_date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_strength ON trading_signals(signal_strength);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_horizon ON trading_signals(time_horizon);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_risk ON trading_signals(risk_level);"
    ]
    
    # Create analytical indexes for complex queries
    analytical_indexes = [
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol_strategy_date ON trading_signals(symbol, strategy, signal_date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_type_confidence ON trading_signals(signal_type, confidence DESC);",
        "CREATE INDEX IF NOT EXISTS idx_trading_signals_performance ON trading_signals(profit_loss_pct DESC) WHERE profit_loss_pct IS NOT NULL;"
    ]
    
    try:
        logger.info("🔧 Creating trading_signals table...")
        
        # Initialize database connection
        init_database()
        
        # Create the main table
        db.execute_query(create_table_query)
        logger.info("✅ trading_signals table created successfully")
        
        # Create performance indexes
        logger.info("🔧 Creating performance indexes...")
        for index_sql in performance_indexes:
            db.execute_query(index_sql)
        logger.info("✅ Performance indexes created")
        
        # Create analytical indexes
        logger.info("🔧 Creating analytical indexes...")
        for index_sql in analytical_indexes:
            db.execute_query(index_sql)
        logger.info("✅ Analytical indexes created")
        
        # Create trigger for updated_at timestamp
        trigger_sql = """
        CREATE OR REPLACE FUNCTION update_trading_signals_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        DROP TRIGGER IF EXISTS trading_signals_updated_at_trigger ON trading_signals;
        CREATE TRIGGER trading_signals_updated_at_trigger
            BEFORE UPDATE ON trading_signals
            FOR EACH ROW
            EXECUTE FUNCTION update_trading_signals_updated_at();
        """
        
        db.execute_query(trigger_sql)
        logger.info("✅ Updated_at trigger created")
        
        # Grant permissions (if needed)
        grant_sql = """
        GRANT SELECT, INSERT, UPDATE, DELETE ON trading_signals TO trading_user;
        GRANT USAGE, SELECT ON SEQUENCE trading_signals_id_seq TO trading_user;
        """
        
        try:
            db.execute_query(grant_sql)
            logger.info("✅ Permissions granted to trading_user")
        except Exception as e:
            logger.warning(f"⚠️ Could not grant permissions (may not be needed): {e}")
        
        logger.info("🎉 trading_signals table migration completed successfully!")
        
        # Verify table creation
        verify_query = """
        SELECT 
            table_name,
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns 
        WHERE table_name = 'trading_signals' 
        ORDER BY ordinal_position;
        """
        
        columns = db.execute_query(verify_query)
        logger.info(f"📊 Table has {len(columns)} columns:")
        for col in columns:
            logger.info(f"   • {col['column_name']}: {col['data_type']} {'(nullable)' if col['is_nullable'] == 'YES' else '(not null)'}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise e

def add_sample_data():
    """Add sample data for testing (optional)"""
    try:
        logger.info("📝 Adding sample data...")
        
        sample_signals = [
            {
                'symbol': 'TQQQ',
                'signal_date': '2025-12-15',
                'signal_type': 'sell',
                'confidence': 0.6,
                'strategy': 'tqqq_swing',
                'price_at_signal': 145.32,
                'sma_50': 148.50,
                'sma_200': 142.80,
                'ema_20': 149.20,
                'rsi_14': 72.5,
                'macd': 1.25,
                'macd_signal': 1.10,
                'signal_strength': 'moderate',
                'time_horizon': 'short_term',
                'risk_level': 'high',
                'signal_reason': 'Sell signal: RSI overbought, EMA20 above SMA50',
                'volatility': 0.25
            },
            {
                'symbol': 'AAPL',
                'signal_date': '2025-12-15',
                'signal_type': 'buy',
                'confidence': 0.8,
                'strategy': 'generic_swing',
                'price_at_signal': 195.45,
                'sma_50': 192.30,
                'sma_200': 188.90,
                'ema_20': 196.80,
                'rsi_14': 28.5,
                'macd': -0.85,
                'macd_signal': -0.95,
                'signal_strength': 'strong',
                'time_horizon': 'medium_term',
                'risk_level': 'medium',
                'signal_reason': 'Buy signal: RSI oversold, SMA50 above SMA200 (bullish)',
                'volatility': 0.18
            }
        ]
        
        insert_query = """
        INSERT INTO trading_signals (
            symbol, signal_date, signal_type, confidence, strategy, 
            price_at_signal, sma_50, sma_200, ema_20, rsi_14, macd, macd_signal,
            signal_strength, time_horizon, risk_level, signal_reason, volatility
        ) VALUES (
            :symbol, :signal_date, :signal_type, :confidence, :strategy,
            :price_at_signal, :sma_50, :sma_200, :ema_20, :rsi_14, :macd, :macd_signal,
            :signal_strength, :time_horizon, :risk_level, :signal_reason, :volatility
        )
        """
        
        for signal in sample_signals:
            db.execute_query(insert_query, signal)
        
        logger.info("✅ Sample data added successfully")
        
    except Exception as e:
        logger.warning(f"⚠️ Could not add sample data: {e}")

if __name__ == "__main__":
    print("🚀 Trading Signals Migration")
    print("=" * 50)
    
    try:
        # Create the table
        success = create_trading_signals_table()
        
        if success:
            # Optionally add sample data for testing
            add_sample_data()
            
            print("\n🎉 Migration completed successfully!")
            print("📊 The trading_signals table is ready for signal storage and analysis.")
            print("\n🔍 You can verify the table with:")
            print("   SELECT COUNT(*) FROM trading_signals;")
            print("   SELECT * FROM trading_signals ORDER BY created_at DESC LIMIT 5;")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
