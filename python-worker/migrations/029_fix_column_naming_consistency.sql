-- Fix column naming consistency across all tables
-- This migration ensures all tables use standard naming: symbol, date (not stock_symbol, trade_date)

-- Fix raw_market_data_daily table
DO $$
BEGIN
    -- Add standard columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'raw_market_data_daily' AND column_name = 'symbol') THEN
        ALTER TABLE raw_market_data_daily ADD COLUMN symbol VARCHAR(10);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'raw_market_data_daily' AND column_name = 'date') THEN
        ALTER TABLE raw_market_data_daily ADD COLUMN date DATE;
    END IF;
    
    -- Add data_source column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'raw_market_data_daily' AND column_name = 'data_source') THEN
        ALTER TABLE raw_market_data_daily ADD COLUMN data_source VARCHAR(50);
    END IF;
    
    -- Add adjusted_close column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'raw_market_data_daily' AND column_name = 'adjusted_close') THEN
        ALTER TABLE raw_market_data_daily ADD COLUMN adjusted_close NUMERIC(12, 4);
    END IF;
    
    -- Migrate data from non-standard columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'raw_market_data_daily' AND column_name = 'stock_symbol') THEN
        UPDATE raw_market_data_daily SET symbol = stock_symbol WHERE symbol IS NULL;
        ALTER TABLE raw_market_data_daily DROP COLUMN stock_symbol;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'raw_market_data_daily' AND column_name = 'trade_date') THEN
        UPDATE raw_market_data_daily SET date = trade_date WHERE date IS NULL;
        ALTER TABLE raw_market_data_daily DROP COLUMN trade_date;
    END IF;
    
    -- Update constraint - drop if exists, then add
    ALTER TABLE raw_market_data_daily DROP CONSTRAINT IF EXISTS raw_market_daily_unique;
    ALTER TABLE raw_market_data_daily ADD CONSTRAINT raw_market_daily_unique UNIQUE (symbol, date, data_source);
END $$;

-- Fix indicators_daily table
DO $$
BEGIN
    -- Add standard columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'symbol') THEN
        ALTER TABLE indicators_daily ADD COLUMN symbol VARCHAR(10);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'date') THEN
        ALTER TABLE indicators_daily ADD COLUMN date DATE;
    END IF;
    
    -- Add indicator_name column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'indicator_name') THEN
        ALTER TABLE indicators_daily ADD COLUMN indicator_name VARCHAR(50);
    END IF;
    
    -- Add data_source column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'data_source') THEN
        ALTER TABLE indicators_daily ADD COLUMN data_source VARCHAR(50);
    END IF;
    
    -- Migrate data from non-standard columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'stock_symbol') THEN
        UPDATE indicators_daily SET symbol = stock_symbol WHERE symbol IS NULL;
        ALTER TABLE indicators_daily DROP COLUMN stock_symbol;
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'indicators_daily' AND column_name = 'trade_date') THEN
        UPDATE indicators_daily SET date = trade_date WHERE date IS NULL;
        ALTER TABLE indicators_daily DROP COLUMN trade_date;
    END IF;
    
    -- Update constraint
    ALTER TABLE indicators_daily DROP CONSTRAINT IF EXISTS indicators_daily_symbol_date_indicator_name_data_source_key;
    ALTER TABLE indicators_daily ADD CONSTRAINT indicators_daily_symbol_date_indicator_name_data_source_key UNIQUE (symbol, date, indicator_name, data_source);
END $$;

-- Fix industry_peers table
DO $$
BEGIN
    -- Add standard column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'industry_peers' AND column_name = 'symbol') THEN
        ALTER TABLE industry_peers ADD COLUMN symbol VARCHAR(10);
    END IF;
    
    -- Migrate data from non-standard column
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'industry_peers' AND column_name = 'stock_symbol') THEN
        UPDATE industry_peers SET symbol = stock_symbol WHERE symbol IS NULL;
        ALTER TABLE industry_peers DROP COLUMN stock_symbol;
    END IF;
    
    -- Update constraint
    ALTER TABLE industry_peers DROP CONSTRAINT IF EXISTS industry_peers_unique;
    ALTER TABLE industry_peers ADD CONSTRAINT industry_peers_unique UNIQUE (symbol, peer_symbol, data_source);
END $$;

-- Fix fundamentals_snapshots table
DO $$
BEGIN
    -- Add standard columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fundamentals_snapshots' AND column_name = 'symbol') THEN
        ALTER TABLE fundamentals_snapshots ADD COLUMN symbol VARCHAR(10);
    END IF;
    
    -- Migrate data from non-standard columns
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'fundamentals_snapshots' AND column_name = 'stock_symbol') THEN
        UPDATE fundamentals_snapshots SET symbol = stock_symbol WHERE symbol IS NULL;
        ALTER TABLE fundamentals_snapshots DROP COLUMN stock_symbol;
    END IF;
    
    -- Note: Keep as_of_date as is since it's specific to fundamentals snapshots
END $$;

-- Fix data_ingestion_state table
DO $$
BEGIN
    -- Add standard column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'data_ingestion_state' AND column_name = 'symbol') THEN
        ALTER TABLE data_ingestion_state ADD COLUMN symbol VARCHAR(10);
    END IF;
    
    -- Add data_source column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'data_ingestion_state' AND column_name = 'data_source') THEN
        ALTER TABLE data_ingestion_state ADD COLUMN data_source VARCHAR(50);
    END IF;
    
    -- Add table_name column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'data_ingestion_state' AND column_name = 'table_name') THEN
        ALTER TABLE data_ingestion_state ADD COLUMN table_name VARCHAR(100);
    END IF;
    
    -- Add dataset column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'data_ingestion_state' AND column_name = 'dataset') THEN
        ALTER TABLE data_ingestion_state ADD COLUMN dataset TEXT;
    END IF;
    
    -- Add interval column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'data_ingestion_state' AND column_name = 'interval') THEN
        ALTER TABLE data_ingestion_state ADD COLUMN interval TEXT;
    END IF;
    
    -- Migrate data from non-standard column
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'data_ingestion_state' AND column_name = 'stock_symbol') THEN
        UPDATE data_ingestion_state SET symbol = stock_symbol WHERE symbol IS NULL;
        ALTER TABLE data_ingestion_state DROP COLUMN stock_symbol;
    END IF;
    
    -- Drop old constraint and create the correct one
    ALTER TABLE data_ingestion_state DROP CONSTRAINT IF EXISTS data_ingestion_state_symbol_data_source_table_name_key;
    ALTER TABLE data_ingestion_state DROP CONSTRAINT IF EXISTS data_ingestion_state_symbol_dataset_interval_key;
    ALTER TABLE data_ingestion_state ADD CONSTRAINT data_ingestion_state_symbol_dataset_interval_key UNIQUE (symbol, dataset, interval);
END $$;

-- Update indexes to use standard column names
DROP INDEX IF EXISTS idx_raw_market_daily_symbol;
CREATE INDEX idx_raw_market_daily_symbol ON raw_market_data_daily(symbol);

DROP INDEX IF EXISTS idx_indicators_daily_symbol;
CREATE INDEX idx_indicators_daily_symbol ON indicators_daily(symbol);

DROP INDEX IF EXISTS idx_industry_peers_symbol;
CREATE INDEX idx_industry_peers_symbol ON industry_peers(symbol);

DROP INDEX IF EXISTS idx_data_ingestion_symbol;
CREATE INDEX idx_data_ingestion_symbol ON data_ingestion_state(symbol);

-- Create missing data_ingestion_runs table
CREATE TABLE IF NOT EXISTS data_ingestion_runs (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    environment VARCHAR(50),
    git_sha VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for data_ingestion_runs
CREATE INDEX IF NOT EXISTS idx_data_ingestion_runs_status ON data_ingestion_runs(status);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_runs_started_at ON data_ingestion_runs(started_at DESC);

-- Create missing data_ingestion_events table
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
);

-- Create indexes for data_ingestion_events
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_run_id ON data_ingestion_events(run_id);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_level ON data_ingestion_events(level);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_event_ts ON data_ingestion_events(event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_symbol ON data_ingestion_events(symbol);
