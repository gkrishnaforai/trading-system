-- Add tables for news, earnings, and industry/peer data
-- PostgreSQL/Supabase compatible

-- stock_news table already defined in 001_baseline_schema.sql

-- Earnings calendar and history
CREATE TABLE IF NOT EXISTS earnings_data (
    earnings_id VARCHAR(255) PRIMARY KEY,
    stock_symbol VARCHAR(10) NOT NULL,
    earnings_date DATE NOT NULL,
    eps_estimate DOUBLE PRECISION,
    eps_actual DOUBLE PRECISION,
    revenue_estimate DOUBLE PRECISION,
    revenue_actual DOUBLE PRECISION,
    surprise_percentage DOUBLE PRECISION, -- EPS surprise %
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(stock_symbol, earnings_date)
);

-- Industry and peer data
CREATE TABLE IF NOT EXISTS industry_peers (
    id SERIAL PRIMARY KEY,
    stock_symbol VARCHAR(10) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    peer_symbol VARCHAR(10) NOT NULL,
    peer_name VARCHAR(255),
    peer_market_cap DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(stock_symbol, peer_symbol)
);

-- Data refresh tracking (tracks when each data type was last refreshed)
CREATE TABLE IF NOT EXISTS data_refresh_tracking (
    id SERIAL PRIMARY KEY,
    stock_symbol VARCHAR(10) NOT NULL,
    data_type VARCHAR(50) NOT NULL, -- 'price_historical', 'price_current', 'fundamentals', 'news', 'earnings', 'industry_peers', 'indicators'
    refresh_mode VARCHAR(50) NOT NULL, -- 'scheduled', 'on_demand', 'periodic', 'live'
    last_refresh TIMESTAMP NOT NULL,
    next_refresh TIMESTAMP,
    status VARCHAR(50) CHECK(status IN ('success', 'failed', 'pending')),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(stock_symbol, data_type, refresh_mode)
);

-- Live/current prices table (for real-time price tracking)
CREATE TABLE IF NOT EXISTS live_prices (
    id SERIAL PRIMARY KEY,
    stock_symbol VARCHAR(10) NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    change DOUBLE PRECISION, -- Price change
    change_percent DOUBLE PRECISION, -- Price change percentage
    volume BIGINT,
    timestamp TIMESTAMP DEFAULT NOW(),
    UNIQUE(stock_symbol, timestamp)
);

-- Create indexes for performance
-- stock_news index already created in 001_baseline_schema.sql
CREATE INDEX IF NOT EXISTS idx_earnings_symbol_date ON earnings_data(stock_symbol, earnings_date DESC);
CREATE INDEX IF NOT EXISTS idx_industry_peers_symbol ON industry_peers(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_refresh_tracking_symbol_type ON data_refresh_tracking(stock_symbol, data_type);
CREATE INDEX IF NOT EXISTS idx_live_prices_symbol_timestamp ON live_prices(stock_symbol, timestamp DESC);

