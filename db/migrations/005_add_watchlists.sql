-- Add Watchlist feature
-- Industry Standard: Watchlist as separate entity from portfolio
-- Supports: Multiple watchlists per user, tagging, alerts, move to portfolio

-- Watchlists table
CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    watchlist_name TEXT NOT NULL,
    description TEXT,
    tags TEXT, -- Comma-separated tags (e.g., "growth,dividend,options")
    is_default BOOLEAN DEFAULT FALSE, -- Only one default per user
    subscription_level_required TEXT CHECK(subscription_level_required IN ('basic', 'pro', 'elite')) DEFAULT 'basic',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Watchlist Items table (stocks/ETFs in watchlist)
CREATE TABLE IF NOT EXISTS watchlist_items (
    item_id TEXT PRIMARY KEY,
    watchlist_id TEXT NOT NULL,
    stock_symbol TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT, -- User notes for this stock in watchlist
    priority INTEGER DEFAULT 0, -- For sorting (higher = more important)
    tags TEXT, -- Item-specific tags
    alert_config JSON, -- Watchlist-level alert configuration for this item
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    UNIQUE(watchlist_id, stock_symbol) -- One stock per watchlist
);

-- Watchlist Alerts table (watchlist-level alerts)
CREATE TABLE IF NOT EXISTS watchlist_alerts (
    alert_id TEXT PRIMARY KEY,
    watchlist_id TEXT NOT NULL,
    stock_symbol TEXT, -- NULL for watchlist-level alerts
    alert_type TEXT NOT NULL, -- 'price_threshold', 'ma_crossover', 'rsi_threshold', 'breakout', etc.
    name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    config JSON NOT NULL, -- Alert-specific configuration
    notification_channels TEXT NOT NULL, -- Comma-separated: 'email,sms'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE
);

-- Watchlist Analytics table (cached watchlist-level metrics)
CREATE TABLE IF NOT EXISTS watchlist_analytics (
    id BIGSERIAL PRIMARY KEY,
    watchlist_id TEXT NOT NULL,
    date DATE NOT NULL,
    total_stocks INTEGER,
    avg_trend_score REAL, -- Average trend strength
    avg_risk_score REAL, -- Average risk score
    bullish_count INTEGER,
    bearish_count INTEGER,
    neutral_count INTEGER,
    high_risk_count INTEGER,
    medium_risk_count INTEGER,
    low_risk_count INTEGER,
    sector_distribution JSON, -- Sector breakdown
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    UNIQUE(watchlist_id, date)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlists_default ON watchlists(user_id, is_default);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol ON watchlist_items(stock_symbol);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_priority ON watchlist_items(watchlist_id, priority DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_watchlist_id ON watchlist_alerts(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_enabled ON watchlist_alerts(watchlist_id, enabled);
CREATE INDEX IF NOT EXISTS idx_watchlist_analytics_watchlist_id ON watchlist_analytics(watchlist_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_analytics_date ON watchlist_analytics(watchlist_id, date DESC);

-- Insert default watchlist for existing users (optional, can be done via application)
-- This is handled by the application layer

