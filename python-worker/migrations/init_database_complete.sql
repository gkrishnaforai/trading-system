-- ===================================================
-- Trading System Database Initialization Script
-- ===================================================
-- This script creates the complete database schema for the trading system
-- Run this to recreate the entire database from scratch
-- ===================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===================================================
-- 1. Core Tables
-- ===================================================

-- Stocks Table (Master Stock Registry)
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

-- Create indexes for stocks
CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_stocks_exchange ON stocks(exchange);
CREATE INDEX IF NOT EXISTS idx_stocks_active ON stocks(is_active);

-- Missing Symbols Queue Table
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

-- ===================================================
-- 2. Market Data Tables
-- ===================================================

-- Raw Market Data Daily Table
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
);

-- Create indexes for raw_market_data_daily
CREATE INDEX IF NOT EXISTS idx_raw_market_daily_symbol ON raw_market_data_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_raw_market_daily_date ON raw_market_data_daily(date);
CREATE INDEX IF NOT EXISTS idx_raw_market_daily_symbol_date ON raw_market_data_daily(symbol, date);

-- Raw Market Data Intraday Table
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
);

-- Create indexes for raw_market_data_intraday
CREATE INDEX IF NOT EXISTS idx_raw_intraday_symbol_ts ON raw_market_data_intraday(symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_raw_intraday_interval ON raw_market_data_intraday(interval);

-- ===================================================
-- 3. Technical Indicators Tables
-- ===================================================

-- Indicators Daily Table
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
);

-- Create indexes for indicators_daily
CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol ON indicators_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_indicators_daily_date ON indicators_daily(date);
CREATE INDEX IF NOT EXISTS idx_indicators_daily_name ON indicators_daily(indicator_name);
CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_date_name ON indicators_daily(symbol, date, indicator_name);

-- ===================================================
-- 4. Fundamentals Tables
-- ===================================================

-- Fundamentals Summary Table
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
);

-- Create indexes for fundamentals_summary
CREATE INDEX IF NOT EXISTS idx_fundamentals_summary_symbol ON fundamentals_summary(symbol);
CREATE INDEX IF NOT EXISTS idx_fundamentals_summary_sector ON fundamentals_summary(sector);
CREATE INDEX IF NOT EXISTS idx_fundamentals_summary_updated ON fundamentals_summary(updated_at);

-- Fundamentals Snapshots Table
CREATE TABLE IF NOT EXISTS fundamentals_snapshots (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    as_of_date DATE NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for fundamentals_snapshots
CREATE INDEX IF NOT EXISTS idx_fundamentals_snapshots_symbol ON fundamentals_snapshots(symbol);
CREATE INDEX IF NOT EXISTS idx_fundamentals_snapshots_as_of_date ON fundamentals_snapshots(as_of_date DESC);

-- ===================================================
-- 5. Financial Statements Tables
-- ===================================================

-- Income Statements Table
CREATE TABLE IF NOT EXISTS income_statements (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    currency VARCHAR(10),
    total_revenue BIGINT,
    gross_profit BIGINT,
    operating_income BIGINT,
    net_income BIGINT,
    research_and_development BIGINT,
    interest_expense BIGINT,
    income_tax_expense BIGINT,
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, fiscal_date_ending, data_source)
);

-- Balance Sheets Table
CREATE TABLE IF NOT EXISTS balance_sheets (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    currency VARCHAR(10),
    total_assets BIGINT,
    total_liabilities BIGINT,
    total_shareholder_equity BIGINT,
    cash_and_cash_equivalents BIGINT,
    short_term_investments BIGINT,
    long_term_debt BIGINT,
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, fiscal_date_ending, data_source)
);

-- Cash Flow Statements Table
CREATE TABLE IF NOT EXISTS cash_flow_statements (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    currency VARCHAR(10),
    operating_cash_flow BIGINT,
    investing_cash_flow BIGINT,
    financing_cash_flow BIGINT,
    free_cash_flow BIGINT,
    capital_expenditures BIGINT,
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, fiscal_date_ending, data_source)
);

-- Financial Ratios Table
CREATE TABLE IF NOT EXISTS financial_ratios (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    fiscal_date_ending DATE NOT NULL,
    currency VARCHAR(10),
    pe_ratio NUMERIC(10, 4),
    pb_ratio NUMERIC(10, 4),
    debt_to_equity NUMERIC(10, 4),
    roe NUMERIC(8, 6),
    current_ratio NUMERIC(8, 6),
    quick_ratio NUMERIC(8, 6),
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, fiscal_date_ending, data_source)
);

-- ===================================================
-- 6. Data Ingestion Tables
-- ===================================================

-- Data Ingestion State Table
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
);

-- Create indexes for data_ingestion_state
CREATE INDEX IF NOT EXISTS idx_data_ingestion_symbol ON data_ingestion_state(symbol);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_source ON data_ingestion_state(data_source);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_status ON data_ingestion_state(status);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_last_ingested ON data_ingestion_state(last_ingested_at);

-- Data Ingestion Runs Table
CREATE TABLE IF NOT EXISTS data_ingestion_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
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

-- Data Ingestion Events Table
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

-- ===================================================
-- 7. Industry & News Tables
-- ===================================================

-- Industry Peers Table
CREATE TABLE IF NOT EXISTS industry_peers (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    peer_symbol VARCHAR(10) NOT NULL,
    industry VARCHAR(100),
    sector VARCHAR(100),
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, peer_symbol, data_source)
);

-- Create indexes for industry_peers
CREATE INDEX IF NOT EXISTS idx_industry_peers_symbol ON industry_peers(symbol);
CREATE INDEX IF NOT EXISTS idx_industry_peers_peer ON industry_peers(peer_symbol);
CREATE INDEX IF NOT EXISTS idx_industry_peers_industry ON industry_peers(industry);

-- Market News Table
CREATE TABLE IF NOT EXISTS market_news (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    title TEXT NOT NULL,
    url TEXT,
    source VARCHAR(100),
    summary TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for market_news
CREATE INDEX IF NOT EXISTS idx_market_news_symbol ON market_news(symbol);
CREATE INDEX IF NOT EXISTS idx_market_news_published_at ON market_news(published_at DESC);

-- ===================================================
-- 8. Signal Tables
-- ===================================================

-- Signals Table
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
);

-- Create indexes for signals
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_type ON signals(symbol, signal_type);

-- ===================================================
-- 9. Triggers and Functions
-- ===================================================

-- Updated At Trigger Function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create updated_at triggers for all relevant tables
CREATE TRIGGER update_stocks_updated_at 
    BEFORE UPDATE ON stocks 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_data_ingestion_state_updated_at 
    BEFORE UPDATE ON data_ingestion_state 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_fundamentals_snapshots_updated_at 
    BEFORE UPDATE ON fundamentals_snapshots 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_income_statements_updated_at 
    BEFORE UPDATE ON income_statements 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_balance_sheets_updated_at 
    BEFORE UPDATE ON balance_sheets 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_cash_flow_statements_updated_at 
    BEFORE UPDATE ON cash_flow_statements 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_financial_ratios_updated_at 
    BEFORE UPDATE ON financial_ratios 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ===================================================
-- 10. Comments and Documentation
-- ===================================================

COMMENT ON TABLE stocks IS 'Master registry of all tradable symbols with company information';
COMMENT ON TABLE raw_market_data_daily IS 'Daily OHLCV price data from various sources';
COMMENT ON TABLE raw_market_data_intraday IS 'Intraday OHLCV price data for various intervals';
COMMENT ON TABLE indicators_daily IS 'Technical indicators (RSI, MACD, SMA, EMA, etc.)';
COMMENT ON TABLE fundamentals_summary IS 'Company overview and key financial metrics';
COMMENT ON TABLE fundamentals_snapshots IS 'Latest fundamentals payload JSON per symbol';
COMMENT ON TABLE data_ingestion_state IS 'Track data loading status and timestamps';
COMMENT ON TABLE data_ingestion_runs IS 'Track each data ingestion run for audit purposes';
COMMENT ON TABLE data_ingestion_events IS 'Individual per-symbol/per-operation events with error details';
COMMENT ON TABLE industry_peers IS 'Industry peer relationships for comparison';
COMMENT ON TABLE market_news IS 'Market news articles and updates';
COMMENT ON TABLE signals IS 'Trading signals generated by various engines';

-- ===================================================
-- 11. Permissions (adjust as needed)
-- ===================================================

-- Uncomment and adjust for your environment
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;

-- ===================================================
-- Database Initialization Complete
-- ===================================================
