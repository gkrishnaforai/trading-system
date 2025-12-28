-- Add market features for TipRanks-like functionality
-- Industry Standard: Market overview, analyst ratings, screeners, movers
-- Supports: Market trends, sector performance, stock comparison

-- Analyst Ratings table
CREATE TABLE IF NOT EXISTS analyst_ratings (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    analyst_name TEXT,
    firm_name TEXT,
    rating TEXT CHECK(rating IN ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')),
    price_target REAL,
    rating_date DATE,
    source TEXT, -- 'alpha_vantage', 'finnhub', 'yahoo', etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, analyst_name, rating_date, source)
);

-- Analyst Consensus (aggregated ratings)
CREATE TABLE IF NOT EXISTS analyst_consensus (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    consensus_rating TEXT CHECK(consensus_rating IN ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')),
    consensus_price_target REAL,
    strong_buy_count INTEGER DEFAULT 0,
    buy_count INTEGER DEFAULT 0,
    hold_count INTEGER DEFAULT 0,
    sell_count INTEGER DEFAULT 0,
    strong_sell_count INTEGER DEFAULT 0,
    total_ratings INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol)
);

-- Market Movers table (top gainers/losers)
CREATE TABLE IF NOT EXISTS market_movers (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    period TEXT NOT NULL CHECK(period IN ('day', 'week', 'month', 'ytd')),
    price_change REAL NOT NULL,
    price_change_percent REAL NOT NULL,
    volume INTEGER,
    market_cap REAL,
    sector TEXT,
    industry TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(stock_symbol, period, timestamp)
);

-- Sector Performance table
CREATE TABLE IF NOT EXISTS sector_performance (
    id BIGSERIAL PRIMARY KEY,
    sector TEXT NOT NULL,
    date DATE NOT NULL,
    total_stocks INTEGER DEFAULT 0,
    avg_price_change REAL DEFAULT 0,
    avg_price_change_percent REAL DEFAULT 0,
    gainers_count INTEGER DEFAULT 0,
    losers_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    top_stocks JSON, -- Top 5 stocks in sector
    market_cap_total REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sector, date)
);

-- Saved Screeners table
CREATE TABLE IF NOT EXISTS saved_screeners (
    screener_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    screener_name TEXT NOT NULL,
    filters JSON NOT NULL, -- Filter criteria
    sort_by TEXT, -- Sort field
    sort_order TEXT CHECK(sort_order IN ('asc', 'desc')) DEFAULT 'desc',
    max_results INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Market Overview snapshot
CREATE TABLE IF NOT EXISTS market_overview (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    market_status TEXT CHECK(market_status IN ('open', 'closed', 'pre_market', 'after_hours')) DEFAULT 'closed',
    sp500_price REAL,
    sp500_change REAL,
    sp500_change_percent REAL,
    nasdaq_price REAL,
    nasdaq_change REAL,
    nasdaq_change_percent REAL,
    dow_price REAL,
    dow_change REAL,
    dow_change_percent REAL,
    total_volume BIGINT,
    advancing_stocks INTEGER,
    declining_stocks INTEGER,
    unchanged_stocks INTEGER,
    new_highs INTEGER,
    new_lows INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date)
);

-- Market Trends table (for heat maps and trend analysis)
CREATE TABLE IF NOT EXISTS market_trends (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    trend_type TEXT NOT NULL CHECK(trend_type IN ('sector', 'industry', 'market_cap', 'overall')),
    category TEXT NOT NULL, -- Sector name, industry name, or market cap category
    trend_score REAL, -- -100 to 100 (negative = bearish, positive = bullish)
    price_change_avg REAL,
    volume_change_avg REAL,
    momentum_score REAL,
    strength TEXT CHECK(strength IN ('very_strong', 'strong', 'moderate', 'weak', 'very_weak')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, trend_type, category)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_analyst_ratings_symbol ON analyst_ratings(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_analyst_ratings_date ON analyst_ratings(rating_date DESC);
CREATE INDEX IF NOT EXISTS idx_analyst_consensus_symbol ON analyst_consensus(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_market_movers_period ON market_movers(period, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_market_movers_symbol ON market_movers(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_sector_performance_date ON sector_performance(date DESC);
CREATE INDEX IF NOT EXISTS idx_sector_performance_sector ON sector_performance(sector);
CREATE INDEX IF NOT EXISTS idx_saved_screeners_user ON saved_screeners(user_id);
CREATE INDEX IF NOT EXISTS idx_market_overview_date ON market_overview(date DESC);
CREATE INDEX IF NOT EXISTS idx_market_trends_date_type ON market_trends(date DESC, trend_type);
CREATE INDEX IF NOT EXISTS idx_market_trends_category ON market_trends(category);

