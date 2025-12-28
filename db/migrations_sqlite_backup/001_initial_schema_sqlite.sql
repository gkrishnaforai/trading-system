-- Complete schema for AI Trading System
-- Supports SQLite (dev) and PostgreSQL/Supabase (prod)
-- Designed for easy migration between databases

-- Users table with subscription tiers
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    subscription_level TEXT NOT NULL DEFAULT 'basic' CHECK(subscription_level IN ('basic', 'pro', 'elite')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolios table
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    portfolio_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Holdings table with position types and strategies
CREATE TABLE IF NOT EXISTS holdings (
    holding_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_entry_price REAL NOT NULL,
    position_type TEXT NOT NULL CHECK(position_type IN ('long', 'short', 'call_option', 'put_option')),
    strategy_tag TEXT, -- e.g., 'covered_call', 'protective_put'
    purchase_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE
);

-- Raw Market Data table
CREATE TABLE IF NOT EXISTS raw_market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_symbol TEXT NOT NULL,
    date DATE NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    fundamental_data JSON, -- JSON snapshot of fundamental data
    options_data JSON, -- JSON snapshot of options data
    news_metadata JSON, -- JSON with headline, date, sentiment_score
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, date)
);

-- Aggregated Indicators table
CREATE TABLE IF NOT EXISTS aggregated_indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_symbol TEXT NOT NULL,
    date DATE NOT NULL,
    -- Moving Averages
    ma7 REAL,
    ma21 REAL,
    sma50 REAL,
    ema20 REAL,
    ema50 REAL,
    sma200 REAL,
    -- Technical Indicators
    atr REAL, -- Average True Range
    macd REAL,
    macd_signal REAL,
    macd_histogram REAL,
    rsi REAL, -- Relative Strength Index
    bb_upper REAL, -- Bollinger Bands upper
    bb_middle REAL, -- Bollinger Bands middle
    bb_lower REAL, -- Bollinger Bands lower
    -- Trend Flags
    long_term_trend TEXT CHECK(long_term_trend IN ('bullish', 'bearish', 'neutral')),
    medium_term_trend TEXT CHECK(medium_term_trend IN ('bullish', 'bearish', 'neutral')),
    -- Signals
    signal TEXT CHECK(signal IN ('buy', 'sell', 'hold')),
    -- Additional Metrics
    pullback_zone_lower REAL,
    pullback_zone_upper REAL,
    momentum_score REAL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, date)
);

-- Portfolio Signals table
CREATE TABLE IF NOT EXISTS portfolio_signals (
    signal_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    date DATE NOT NULL,
    signal_type TEXT NOT NULL CHECK(signal_type IN ('buy', 'sell', 'hold', 'covered_call', 'protective_put')),
    suggested_allocation REAL, -- Percentage (0-100)
    stop_loss REAL,
    confidence_score REAL, -- 0-1
    subscription_level_required TEXT CHECK(subscription_level_required IN ('basic', 'pro', 'elite')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE
);

-- LLM Generated Reports table
CREATE TABLE IF NOT EXISTS llm_generated_reports (
    report_id TEXT PRIMARY KEY,
    portfolio_id TEXT, -- NULL if stock-level report
    stock_symbol TEXT, -- NULL if portfolio-level report
    generated_content TEXT NOT NULL, -- JSON or text content
    report_type TEXT CHECK(report_type IN ('portfolio_analysis', 'stock_analysis', 'signal_explanation', 'blog_post')),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE SET NULL
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_id ON holdings(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON holdings(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_raw_market_data_symbol_date ON raw_market_data(stock_symbol, date);
CREATE INDEX IF NOT EXISTS idx_aggregated_indicators_symbol_date ON aggregated_indicators(stock_symbol, date);
CREATE INDEX IF NOT EXISTS idx_portfolio_signals_portfolio_id ON portfolio_signals(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_signals_symbol ON portfolio_signals(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_portfolio_signals_date ON portfolio_signals(date);
CREATE INDEX IF NOT EXISTS idx_llm_reports_portfolio_id ON llm_generated_reports(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_llm_reports_symbol ON llm_generated_reports(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_users_subscription_level ON users(subscription_level);
