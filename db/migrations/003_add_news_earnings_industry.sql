-- Add tables for news, earnings, and industry/peer data
-- Supports comprehensive data management with refresh tracking

-- News articles table
CREATE TABLE IF NOT EXISTS stock_news (
    news_id TEXT PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    publisher TEXT,
    link TEXT,
    published_date TIMESTAMP,
    sentiment_score REAL, -- -1 to 1 (negative to positive)
    related_symbols TEXT, -- JSON array of related symbols
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Earnings calendar and history
CREATE TABLE IF NOT EXISTS earnings_data (
    earnings_id TEXT PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    eps_estimate REAL,
    eps_actual REAL,
    revenue_estimate REAL,
    revenue_actual REAL,
    surprise_percentage REAL, -- EPS surprise %
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, earnings_date)
);

-- Industry and peer data
CREATE TABLE IF NOT EXISTS industry_peers (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    peer_symbol TEXT NOT NULL,
    peer_name TEXT,
    peer_market_cap REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, peer_symbol)
);

-- Data refresh tracking (tracks when each data type was last refreshed)
CREATE TABLE IF NOT EXISTS data_refresh_tracking (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    data_type TEXT NOT NULL, -- 'price_historical', 'price_current', 'fundamentals', 'news', 'earnings', 'industry_peers', 'indicators'
    refresh_mode TEXT NOT NULL, -- 'scheduled', 'on_demand', 'periodic', 'live'
    last_refresh TIMESTAMP NOT NULL,
    next_refresh TIMESTAMP,
    status TEXT CHECK(status IN ('success', 'failed', 'pending')),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, data_type, refresh_mode)
);

-- Live/current prices table (for real-time price tracking)
CREATE TABLE IF NOT EXISTS live_prices (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    price REAL NOT NULL,
    change REAL, -- Price change
    change_percent REAL, -- Price change percentage
    volume INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, timestamp)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_stock_news_symbol_date ON stock_news(stock_symbol, published_date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol_date ON earnings_data(stock_symbol, earnings_date DESC);
CREATE INDEX IF NOT EXISTS idx_industry_peers_symbol ON industry_peers(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_refresh_tracking_symbol_type ON data_refresh_tracking(stock_symbol, data_type);
CREATE INDEX IF NOT EXISTS idx_live_prices_symbol_timestamp ON live_prices(stock_symbol, timestamp DESC);

