-- Add watchlist tables
-- PostgreSQL/Supabase compatible

-- Watchlists table
CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    watchlist_name VARCHAR(255) NOT NULL,
    description TEXT,
    tags VARCHAR(255),
    is_default BOOLEAN DEFAULT FALSE,
    subscription_level_required VARCHAR(50) DEFAULT 'basic' CHECK(subscription_level_required IN ('basic', 'pro', 'elite')),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Watchlist Items table
CREATE TABLE IF NOT EXISTS watchlist_items (
    item_id VARCHAR(255) PRIMARY KEY,
    watchlist_id VARCHAR(255) NOT NULL,
    stock_symbol VARCHAR(10) NOT NULL,
    added_at TIMESTAMP DEFAULT NOW(),
    notes TEXT,
    priority INTEGER DEFAULT 0,
    tags VARCHAR(255),
    price_when_added DOUBLE PRECISION,
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    UNIQUE(watchlist_id, stock_symbol)
);

-- Watchlist Alerts table
CREATE TABLE IF NOT EXISTS watchlist_alerts (
    alert_id VARCHAR(255) PRIMARY KEY,
    watchlist_id VARCHAR(255) NOT NULL,
    item_id VARCHAR(255),
    alert_type VARCHAR(50) NOT NULL,
    threshold_value DOUBLE PRECISION,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES watchlist_items(item_id) ON DELETE CASCADE
);

-- Watchlist Analytics table
CREATE TABLE IF NOT EXISTS watchlist_analytics (
    analytics_id VARCHAR(255) PRIMARY KEY,
    watchlist_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    total_items INTEGER DEFAULT 0,
    items_with_signals INTEGER DEFAULT 0,
    avg_sentiment_score DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    UNIQUE(watchlist_id, date)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol ON watchlist_items(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_watchlist_id ON watchlist_alerts(watchlist_id);

