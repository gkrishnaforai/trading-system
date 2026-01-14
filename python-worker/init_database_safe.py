#!/usr/bin/env python3
"""
Step-by-Step Database Initialization Script
Creates tables in the correct order to avoid dependency issues
"""

import os
import sys
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv

def create_table_safely(cursor, table_name, sql):
    """Create a table safely with error handling"""
    try:
        cursor.execute(sql)
        print(f"   ✅ Created table: {table_name}")
        return True
    except Exception as e:
        if "already exists" in str(e):
            print(f"   ⏭️  Table already exists: {table_name}")
            return True
        else:
            print(f"   ❌ Error creating {table_name}: {e}")
            return False

def create_index_safely(cursor, index_name, sql):
    """Create an index safely with error handling"""
    try:
        cursor.execute(sql)
        print(f"   ✅ Created index: {index_name}")
        return True
    except Exception as e:
        if "already exists" in str(e) or "does not exist" in str(e):
            print(f"   ⏭️  Index issue (skipped): {index_name}")
            return True
        else:
            print(f"   ❌ Error creating index {index_name}: {e}")
            return False

def initialize_database_step_by_step():
    """Initialize database step by step to avoid dependency issues"""
    
    # Load environment variables
    load_dotenv()
    
    # Get database connection string
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL not found in environment variables")
        return False
    
    print("🚀 Step-by-Step Database Initialization...")
    print("=" * 60)
    
    try:
        # Connect to PostgreSQL database
        print("📡 Connecting to database...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Enable UUID extension
        print("🔧 Enabling UUID extension...")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
        
        # Step 1: Create core tables first
        print("\n📊 Step 1: Creating Core Tables...")
        
        core_tables = [
            ("stocks", """
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
                    has_fundamentals BOOLEAN DEFAULT FALSE,
                    has_earnings BOOLEAN DEFAULT FALSE,
                    has_market_data BOOLEAN DEFAULT FALSE,
                    has_indicators BOOLEAN DEFAULT FALSE,
                    last_fundamentals_update TIMESTAMP,
                    last_earnings_update TIMESTAMP,
                    last_market_data_update TIMESTAMP,
                    last_indicators_update TIMESTAMP
                )
            """),
            
            ("missing_symbols_queue", """
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
                )
            """),
            
            ("raw_market_data_daily", """
                CREATE TABLE IF NOT EXISTS raw_market_data_daily (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    open NUMERIC(12, 4),
                    high NUMERIC(12, 4),
                    low NUMERIC(12, 4),
                    close NUMERIC(12, 4),
                    volume BIGINT,
                    adjusted_close NUMERIC(12, 4),
                    data_source VARCHAR(50) DEFAULT 'yahoo_finance',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date, data_source)
                )
            """),
            
            ("raw_market_data_intraday", """
                CREATE TABLE IF NOT EXISTS raw_market_data_intraday (
                    id BIGSERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    interval VARCHAR(10) NOT NULL,
                    open NUMERIC(12, 4),
                    high NUMERIC(12, 4),
                    low NUMERIC(12, 4),
                    close NUMERIC(12, 4),
                    volume BIGINT,
                    data_source VARCHAR(50) DEFAULT 'yahoo_finance',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(symbol, ts, interval, data_source)
                )
            """),
            
            ("indicators_daily", """
                CREATE TABLE IF NOT EXISTS indicators_daily (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    indicator_name VARCHAR(50) NOT NULL,
                    indicator_value NUMERIC(12, 6),
                    time_period INTEGER,
                    data_source VARCHAR(50) DEFAULT 'yahoo_finance',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date, indicator_name, data_source)
                )
            """),
            
            ("data_ingestion_state", """
                CREATE TABLE IF NOT EXISTS data_ingestion_state (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    data_source VARCHAR(50) NOT NULL,
                    table_name VARCHAR(100) NOT NULL,
                    dataset TEXT,
                    interval TEXT,
                    last_ingested_at TIMESTAMP,
                    records_count INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, data_source, table_name)
                )
            """),
            
            ("data_ingestion_runs", """
                CREATE TABLE IF NOT EXISTS data_ingestion_runs (
                    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ,
                    status VARCHAR(20) NOT NULL DEFAULT 'running',
                    environment VARCHAR(50),
                    git_sha VARCHAR(100),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """),
            
            ("data_ingestion_events", """
                CREATE TABLE IF NOT EXISTS data_ingestion_events (
                    id BIGSERIAL PRIMARY KEY,
                    run_id UUID NOT NULL,
                    event_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    level VARCHAR(20) NOT NULL,
                    provider VARCHAR(50),
                    operation VARCHAR(100),
                    symbol VARCHAR(10),
                    duration_ms INTEGER,
                    records_in INTEGER,
                    records_saved INTEGER,
                    message TEXT,
                    error_type VARCHAR(100),
                    error_message TEXT,
                    root_cause_type VARCHAR(100),
                    root_cause_message TEXT,
                    context JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """),
            
            ("fundamentals_summary", """
                CREATE TABLE IF NOT EXISTS fundamentals_summary (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    name VARCHAR(255),
                    sector VARCHAR(100),
                    industry VARCHAR(100),
                    market_cap BIGINT,
                    pe_ratio NUMERIC(10, 4),
                    pb_ratio NUMERIC(10, 4),
                    eps NUMERIC(10, 4),
                    beta NUMERIC(6, 4),
                    dividend_yield NUMERIC(8, 6),
                    revenue_ttm BIGINT,
                    gross_profit_ttm BIGINT,
                    operating_margin_ttm NUMERIC(8, 6),
                    profit_margin NUMERIC(8, 6),
                    roe NUMERIC(8, 6),
                    debt_to_equity NUMERIC(10, 4),
                    price_to_sales NUMERIC(10, 4),
                    ev_to_revenue NUMERIC(10, 4),
                    ev_to_ebitda NUMERIC(10, 4),
                    price_to_book NUMERIC(10, 4),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    updated_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, data_source)
                )
            """),
            
            ("fundamentals_snapshots", """
                CREATE TABLE IF NOT EXISTS fundamentals_snapshots (
                    id BIGSERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL UNIQUE,
                    as_of_date DATE NOT NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """),
            
            ("industry_peers", """
                CREATE TABLE IF NOT EXISTS industry_peers (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    peer_symbol VARCHAR(10) NOT NULL,
                    industry VARCHAR(100),
                    sector VARCHAR(100),
                    data_source VARCHAR(50) DEFAULT 'alphavantage',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, peer_symbol, data_source)
                )
            """),
            
            ("market_news", """
                CREATE TABLE IF NOT EXISTS market_news (
                    id BIGSERIAL PRIMARY KEY,
                    symbol VARCHAR(10),
                    title TEXT NOT NULL,
                    url TEXT,
                    source VARCHAR(100),
                    summary TEXT,
                    published_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """),
            
            ("macro_market_data", """
                CREATE TABLE IF NOT EXISTS macro_market_data (
                    id SERIAL PRIMARY KEY,
                    data_date DATE NOT NULL UNIQUE,
                    vix_close NUMERIC(8, 2),
                    nasdaq_symbol VARCHAR(10),
                    nasdaq_close NUMERIC(12, 4),
                    nasdaq_sma50 NUMERIC(12, 4),
                    nasdaq_sma200 NUMERIC(12, 4),
                    tnx_yield NUMERIC(6, 4),
                    irx_yield NUMERIC(6, 4),
                    yield_curve_spread NUMERIC(6, 4),
                    sp500_above_50d_pct NUMERIC(5, 4),
                    source VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """),
            
            ("signals", """
                CREATE TABLE IF NOT EXISTS signals (
                    id BIGSERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    signal_type VARCHAR(50) NOT NULL,
                    signal_value VARCHAR(20) NOT NULL,
                    confidence NUMERIC(3, 2),
                    price_at_signal NUMERIC(12, 4),
                    timestamp TIMESTAMPTZ NOT NULL,
                    engine_name VARCHAR(100),
                    reasoning TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(symbol, signal_type, timestamp, engine_name)
                )
            """)
        ]
        
        # Create core tables
        success_count = 0
        for table_name, sql in core_tables:
            if create_table_safely(cursor, table_name, sql):
                success_count += 1
        
        print(f"📊 Core tables created: {success_count}/{len(core_tables)}")
        
        # Step 2: Create indexes after tables exist
        print("\n🔍 Step 2: Creating Indexes...")
        
        indexes = [
            ("idx_stocks_symbol", "CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol)"),
            ("idx_stocks_sector", "CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector)"),
            ("idx_stocks_exchange", "CREATE INDEX IF NOT EXISTS idx_stocks_exchange ON stocks(exchange)"),
            ("idx_stocks_active", "CREATE INDEX IF NOT EXISTS idx_stocks_active ON stocks(is_active)"),
            ("idx_raw_market_daily_symbol", "CREATE INDEX IF NOT EXISTS idx_raw_market_daily_symbol ON raw_market_data_daily(symbol)"),
            ("idx_raw_market_daily_date", "CREATE INDEX IF NOT EXISTS idx_raw_market_daily_date ON raw_market_data_daily(date)"),
            ("idx_raw_market_daily_symbol_date", "CREATE INDEX IF NOT EXISTS idx_raw_market_daily_symbol_date ON raw_market_data_daily(symbol, date)"),
            ("idx_indicators_daily_symbol", "CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol ON indicators_daily(symbol)"),
            ("idx_indicators_daily_date", "CREATE INDEX IF NOT EXISTS idx_indicators_daily_date ON indicators_daily(date)"),
            ("idx_indicators_daily_name", "CREATE INDEX IF NOT EXISTS idx_indicators_daily_name ON indicators_daily(indicator_name)"),
            ("idx_data_ingestion_runs_status", "CREATE INDEX IF NOT EXISTS idx_data_ingestion_runs_status ON data_ingestion_runs(status)"),
            ("idx_data_ingestion_runs_started_at", "CREATE INDEX IF NOT EXISTS idx_data_ingestion_runs_started_at ON data_ingestion_runs(started_at DESC)"),
            ("idx_fundamentals_summary_symbol", "CREATE INDEX IF NOT EXISTS idx_fundamentals_summary_symbol ON fundamentals_summary(symbol)"),
            ("idx_fundamentals_snapshots_symbol", "CREATE INDEX IF NOT EXISTS idx_fundamentals_snapshots_symbol ON fundamentals_snapshots(symbol)"),
            ("idx_industry_peers_symbol", "CREATE INDEX IF NOT EXISTS idx_industry_peers_symbol ON industry_peers(symbol)"),
            ("idx_market_news_symbol", "CREATE INDEX IF NOT EXISTS idx_market_news_symbol ON market_news(symbol)"),
            ("idx_market_news_published_at", "CREATE INDEX IF NOT EXISTS idx_market_news_published_at ON market_news(published_at DESC)"),
            ("idx_macro_date", "CREATE INDEX IF NOT EXISTS idx_macro_date ON macro_market_data(data_date DESC)"),
            ("idx_signals_symbol", "CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)"),
            ("idx_signals_type", "CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type)"),
            ("idx_signals_timestamp", "CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC)")
        ]
        
        index_success = 0
        for index_name, sql in indexes:
            if create_index_safely(cursor, index_name, sql):
                index_success += 1
        
        print(f"🔍 Indexes created: {index_success}/{len(indexes)}")
        
        # Step 3: Create triggers
        print("\n⚡ Step 3: Creating Triggers...")
        
        # Create update function
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        print("   ✅ Created update_updated_at_column function")
        
        # Create triggers for tables with updated_at columns
        triggers = [
            ("update_stocks_updated_at", "CREATE TRIGGER update_stocks_updated_at BEFORE UPDATE ON stocks FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();"),
            ("update_data_ingestion_state_updated_at", "CREATE TRIGGER update_data_ingestion_state_updated_at BEFORE UPDATE ON data_ingestion_state FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();"),
            ("update_fundamentals_snapshots_updated_at", "CREATE TRIGGER update_fundamentals_snapshots_updated_at BEFORE UPDATE ON fundamentals_snapshots FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();")
        ]
        
        trigger_success = 0
        for trigger_name, sql in triggers:
            if create_index_safely(cursor, trigger_name, sql):
                trigger_success += 1
        
        print(f"⚡ Triggers created: {trigger_success}/{len(triggers)}")
        
        # Step 4: Verify tables exist
        print("\n✅ Step 4: Verification...")
        
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"📊 Total tables in database: {len(tables)}")
        for table in tables:
            print(f"   ✅ {table}")
        
        # Close connection
        cursor.close()
        conn.close()
        
        print("\n🎉 Database initialization completed successfully!")
        print("🔄 You can now restart the python-worker service")
        
        return True
        
    except OperationalError as e:
        print(f"❌ Database connection error: {e}")
        print("🔧 Please check your DATABASE_URL configuration")
        return False
        
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function"""
    success = initialize_database_step_by_step()
    
    if success:
        print("\n📋 Next Steps:")
        print("1. Restart the python-worker service:")
        print("   docker-compose restart python-worker")
        print("2. Run bulk stock loading:")
        print("   curl -X POST http://localhost:8001/api/v1/bulk/stocks/load/popular")
        print("3. Test the Streamlit UI - stock selector should work!")
        sys.exit(0)
    else:
        print("\n❌ Database initialization failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
