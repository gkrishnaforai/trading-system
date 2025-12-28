-- Alpha Vantage Database Tables Migration
-- Creates all tables required for Alpha Vantage data loading

-- Fundamentals Summary Table
-- Company overview and key metrics
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

-- Fundamentals Table
-- Detailed financial statements (income statement, balance sheet, cash flow, earnings)
CREATE TABLE IF NOT EXISTS fundamentals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    report_type VARCHAR(50) NOT NULL, -- 'income_statement', 'balance_sheet', 'cash_flow', 'earnings'
    fiscal_date_ending DATE,
    reported_date DATE,
    reported_currency VARCHAR(10),
    
    -- Income Statement fields
    total_revenue BIGINT,
    gross_profit BIGINT,
    operating_income BIGINT,
    net_income BIGINT,
    research_and_development BIGINT,
    selling_general_and_admin BIGINT,
    interest_expense BIGINT,
    income_tax_expense BIGINT,
    
    -- Balance Sheet fields
    total_assets BIGINT,
    total_liabilities BIGINT,
    total_shareholder_equity BIGINT,
    cash_and_cash_equivalents BIGINT,
    short_term_investments BIGINT,
    long_term_debt BIGINT,
    
    -- Cash Flow fields
    operating_cash_flow BIGINT,
    investing_cash_flow BIGINT,
    financing_cash_flow BIGINT,
    free_cash_flow BIGINT,
    capital_expenditures BIGINT,
    
    -- Earnings fields
    reported_eps NUMERIC(10, 4),
    estimated_eps NUMERIC(10, 4),
    surprise NUMERIC(10, 4),
    surprise_percentage NUMERIC(8, 4),
    
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    updated_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, report_type, fiscal_date_ending, data_source)
);

-- Create indexes for fundamentals
CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol ON fundamentals(symbol);
CREATE INDEX IF NOT EXISTS idx_fundamentals_report_type ON fundamentals(report_type);
CREATE INDEX IF NOT EXISTS idx_fundamentals_fiscal_date ON fundamentals(fiscal_date_ending);
CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol_type ON fundamentals(symbol, report_type);

-- Raw Market Data Daily Table
-- Daily OHLCV price data
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
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, date, data_source)
);

-- Create indexes for raw_market_data_daily
CREATE INDEX IF NOT EXISTS idx_raw_market_daily_symbol ON raw_market_data_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_raw_market_daily_date ON raw_market_data_daily(date);
CREATE INDEX IF NOT EXISTS idx_raw_market_daily_symbol_date ON raw_market_data_daily(symbol, date);

-- Indicators Daily Table
-- Technical indicators (RSI, MACD, SMA, EMA, etc.)
CREATE TABLE IF NOT EXISTS indicators_daily (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    indicator_value NUMERIC(12, 6),
    time_period INTEGER,
    data_source VARCHAR(50) DEFAULT 'alphavantage',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, date, indicator_name, data_source)
);

-- Create indexes for indicators_daily
CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol ON indicators_daily(symbol);
CREATE INDEX IF NOT EXISTS idx_indicators_daily_date ON indicators_daily(date);
CREATE INDEX IF NOT EXISTS idx_indicators_daily_name ON indicators_daily(indicator_name);
CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_date_name ON indicators_daily(symbol, date, indicator_name);

-- Data Ingestion State Table
-- Track data loading status and timestamps
CREATE TABLE IF NOT EXISTS data_ingestion_state (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    data_source VARCHAR(50) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    last_ingested_at TIMESTAMP,
    records_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'success', 'failed'
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

-- Industry Peers Table
-- Store industry peer relationships
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

-- Add comments for documentation
COMMENT ON TABLE fundamentals_summary IS 'Company overview and key financial metrics from Alpha Vantage';
COMMENT ON TABLE fundamentals IS 'Detailed financial statements (income, balance sheet, cash flow, earnings)';
COMMENT ON TABLE raw_market_data_daily IS 'Daily OHLCV price data from Alpha Vantage';
COMMENT ON TABLE indicators_daily IS 'Technical indicators (RSI, MACD, SMA, EMA, etc.)';
COMMENT ON TABLE data_ingestion_state IS 'Track data loading status and timestamps';
COMMENT ON TABLE industry_peers IS 'Industry peer relationships for comparison';

-- Create updated_at trigger function (if not exists)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at
CREATE TRIGGER update_fundamentals_summary_updated_at 
    BEFORE UPDATE ON fundamentals_summary 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_fundamentals_updated_at 
    BEFORE UPDATE ON fundamentals 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_data_ingestion_state_updated_at 
    BEFORE UPDATE ON data_ingestion_state 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions (adjust username as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;
