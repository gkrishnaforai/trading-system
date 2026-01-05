-- Create stocks table for comprehensive stock master data
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

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_stocks_exchange ON stocks(exchange);
CREATE INDEX IF NOT EXISTS idx_stocks_active ON stocks(is_active);

-- Create missing symbols queue table
CREATE TABLE IF NOT EXISTS missing_symbols_queue (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    source_table VARCHAR(50) NOT NULL, -- 'earnings_calendar', 'market_news', etc.
    source_record_id INTEGER,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'processing', 'completed', 'failed'
    error_message TEXT,
    attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    UNIQUE(symbol, source_table, source_record_id)
);

CREATE INDEX IF NOT EXISTS idx_missing_symbols_status ON missing_symbols_queue(status);
CREATE INDEX IF NOT EXISTS idx_missing_symbols_discovered ON missing_symbols_queue(discovered_at);

-- Add foreign key constraints if stocks table is referenced
-- Note: These will be added in separate migration files to avoid circular dependencies
