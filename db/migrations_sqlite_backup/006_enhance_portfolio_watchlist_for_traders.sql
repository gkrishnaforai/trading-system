-- Enhance Portfolio and Watchlist schemas for traders and analysts
-- Industry Standard: Comprehensive fields for professional trading and analysis
-- Based on industry best practices (Bloomberg Terminal, TradingView, Interactive Brokers, etc.)

-- ==================== Portfolio Enhancements ====================

-- Add portfolio metadata for traders/analysts
ALTER TABLE portfolios ADD COLUMN portfolio_type TEXT CHECK(portfolio_type IN ('long_term', 'swing', 'day_trading', 'options', 'crypto', 'mixed')) DEFAULT 'mixed';
ALTER TABLE portfolios ADD COLUMN currency TEXT DEFAULT 'USD';
ALTER TABLE portfolios ADD COLUMN benchmark_symbol TEXT; -- e.g., 'SPY', 'QQQ' for comparison
ALTER TABLE portfolios ADD COLUMN target_allocation JSON; -- Target sector/asset allocation
ALTER TABLE portfolios ADD COLUMN risk_tolerance TEXT CHECK(risk_tolerance IN ('conservative', 'moderate', 'aggressive')) DEFAULT 'moderate';
ALTER TABLE portfolios ADD COLUMN investment_horizon TEXT CHECK(investment_horizon IN ('short_term', 'medium_term', 'long_term')) DEFAULT 'medium_term';
ALTER TABLE portfolios ADD COLUMN is_taxable BOOLEAN DEFAULT TRUE; -- Taxable vs tax-advantaged account
ALTER TABLE portfolios ADD COLUMN tax_strategy TEXT; -- Tax-loss harvesting, etc.
ALTER TABLE portfolios ADD COLUMN rebalancing_frequency TEXT CHECK(rebalancing_frequency IN ('daily', 'weekly', 'monthly', 'quarterly', 'annually', 'manual')) DEFAULT 'manual';
ALTER TABLE portfolios ADD COLUMN last_rebalanced DATE;
ALTER TABLE portfolios ADD COLUMN color_code TEXT; -- For UI organization
ALTER TABLE portfolios ADD COLUMN is_archived BOOLEAN DEFAULT FALSE; -- Archive old portfolios
ALTER TABLE portfolios ADD COLUMN metadata JSON; -- Additional flexible metadata

-- ==================== Holdings Enhancements ====================

-- Add comprehensive holding fields for traders/analysts
ALTER TABLE holdings ADD COLUMN current_price REAL; -- Cached current price
ALTER TABLE holdings ADD COLUMN current_value REAL; -- quantity * current_price
ALTER TABLE holdings ADD COLUMN cost_basis REAL; -- Total cost basis (quantity * avg_entry_price)
ALTER TABLE holdings ADD COLUMN unrealized_gain_loss REAL; -- Unrealized P&L
ALTER TABLE holdings ADD COLUMN unrealized_gain_loss_percent REAL; -- Unrealized P&L %
ALTER TABLE holdings ADD COLUMN realized_gain_loss REAL DEFAULT 0; -- Realized P&L (for closed positions)
ALTER TABLE holdings ADD COLUMN exit_price REAL; -- Exit price (for closed positions)
ALTER TABLE holdings ADD COLUMN exit_date DATE; -- Exit date (for closed positions)
ALTER TABLE holdings ADD COLUMN commission REAL DEFAULT 0; -- Trading commission
ALTER TABLE holdings ADD COLUMN tax_lot_id TEXT; -- For tax lot tracking
ALTER TABLE holdings ADD COLUMN cost_basis_method TEXT CHECK(cost_basis_method IN ('FIFO', 'LIFO', 'average', 'specific_lot')) DEFAULT 'average';
ALTER TABLE holdings ADD COLUMN sector TEXT; -- Cached sector for quick filtering
ALTER TABLE holdings ADD COLUMN industry TEXT; -- Cached industry
ALTER TABLE holdings ADD COLUMN market_cap_category TEXT CHECK(market_cap_category IN ('mega', 'large', 'mid', 'small', 'micro')) DEFAULT NULL;
ALTER TABLE holdings ADD COLUMN dividend_yield REAL; -- Cached dividend yield
ALTER TABLE holdings ADD COLUMN target_price REAL; -- Target price for exit
ALTER TABLE holdings ADD COLUMN stop_loss_price REAL; -- Stop loss price
ALTER TABLE holdings ADD COLUMN take_profit_price REAL; -- Take profit price
ALTER TABLE holdings ADD COLUMN allocation_percent REAL; -- % of portfolio
ALTER TABLE holdings ADD COLUMN target_allocation_percent REAL; -- Target % allocation
ALTER TABLE holdings ADD COLUMN last_updated_price TIMESTAMP; -- When price was last updated
ALTER TABLE holdings ADD COLUMN is_closed BOOLEAN DEFAULT FALSE; -- Closed position flag
ALTER TABLE holdings ADD COLUMN closed_reason TEXT; -- Why position was closed
ALTER TABLE holdings ADD COLUMN metadata JSON; -- Additional flexible metadata

-- ==================== Watchlist Enhancements ====================

-- Add watchlist metadata for traders/analysts
ALTER TABLE watchlists ADD COLUMN color_code TEXT; -- For UI organization
ALTER TABLE watchlists ADD COLUMN sort_order INTEGER DEFAULT 0; -- Custom sort order
ALTER TABLE watchlists ADD COLUMN view_preferences JSON; -- Column visibility, sort preferences
ALTER TABLE watchlists ADD COLUMN is_archived BOOLEAN DEFAULT FALSE; -- Archive old watchlists
ALTER TABLE watchlists ADD COLUMN metadata JSON; -- Additional flexible metadata

-- ==================== Watchlist Items Enhancements ====================

-- Add comprehensive watchlist item fields for traders/analysts
ALTER TABLE watchlist_items ADD COLUMN price_when_added REAL; -- Price when added to watchlist
ALTER TABLE watchlist_items ADD COLUMN target_price REAL; -- Target entry price
ALTER TABLE watchlist_items ADD COLUMN target_date DATE; -- Target date for entry
ALTER TABLE watchlist_items ADD COLUMN watch_reason TEXT; -- Why watching this stock
ALTER TABLE watchlist_items ADD COLUMN analyst_rating TEXT CHECK(analyst_rating IN ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')) DEFAULT NULL;
ALTER TABLE watchlist_items ADD COLUMN analyst_price_target REAL; -- Analyst consensus price target
ALTER TABLE watchlist_items ADD COLUMN current_price REAL; -- Cached current price
ALTER TABLE watchlist_items ADD COLUMN price_change_since_added REAL; -- Price change since added
ALTER TABLE watchlist_items ADD COLUMN price_change_percent_since_added REAL; -- % change since added
ALTER TABLE watchlist_items ADD COLUMN sector TEXT; -- Cached sector
ALTER TABLE watchlist_items ADD COLUMN industry TEXT; -- Cached industry
ALTER TABLE watchlist_items ADD COLUMN market_cap_category TEXT CHECK(market_cap_category IN ('mega', 'large', 'mid', 'small', 'micro')) DEFAULT NULL;
ALTER TABLE watchlist_items ADD COLUMN dividend_yield REAL; -- Cached dividend yield
ALTER TABLE watchlist_items ADD COLUMN earnings_date DATE; -- Next earnings date
ALTER TABLE watchlist_items ADD COLUMN last_updated_price TIMESTAMP; -- When price was last updated
ALTER TABLE watchlist_items ADD COLUMN metadata JSON; -- Additional flexible metadata

-- ==================== Portfolio Performance Tracking ====================

-- Portfolio performance snapshot table (daily/weekly/monthly snapshots)
CREATE TABLE IF NOT EXISTS portfolio_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    total_value REAL NOT NULL, -- Total portfolio value
    cost_basis REAL NOT NULL, -- Total cost basis
    total_gain_loss REAL NOT NULL, -- Total P&L
    total_gain_loss_percent REAL NOT NULL, -- Total P&L %
    cash_balance REAL DEFAULT 0, -- Cash in portfolio
    invested_amount REAL NOT NULL, -- Amount invested
    day_change REAL, -- Day change
    day_change_percent REAL, -- Day change %
    week_change REAL, -- Week change
    week_change_percent REAL, -- Week change %
    month_change REAL, -- Month change
    month_change_percent REAL, -- Month change %
    year_change REAL, -- Year change
    year_change_percent REAL, -- Year change %
    max_drawdown REAL, -- Maximum drawdown
    sharpe_ratio REAL, -- Sharpe ratio
    beta REAL, -- Portfolio beta
    alpha REAL, -- Portfolio alpha
    sector_allocation JSON, -- Sector breakdown
    top_holdings JSON, -- Top 10 holdings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    UNIQUE(portfolio_id, snapshot_date)
);

-- ==================== Watchlist Performance Tracking ====================

-- Watchlist performance snapshot table
CREATE TABLE IF NOT EXISTS watchlist_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    total_stocks INTEGER NOT NULL,
    avg_price_change REAL, -- Average price change
    avg_price_change_percent REAL, -- Average % change
    bullish_count INTEGER,
    bearish_count INTEGER,
    neutral_count INTEGER,
    high_risk_count INTEGER,
    medium_risk_count INTEGER,
    low_risk_count INTEGER,
    sector_distribution JSON, -- Sector breakdown
    top_gainers JSON, -- Top gainers
    top_losers JSON, -- Top losers
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
    UNIQUE(watchlist_id, snapshot_date)
);

-- ==================== Trading Activity Log ====================

-- Trading activity log for audit and analysis
CREATE TABLE IF NOT EXISTS trading_activity (
    activity_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    portfolio_id TEXT,
    watchlist_id TEXT,
    stock_symbol TEXT NOT NULL,
    activity_type TEXT NOT NULL CHECK(activity_type IN ('buy', 'sell', 'add_to_watchlist', 'remove_from_watchlist', 'move_to_portfolio', 'alert_triggered', 'signal_generated')),
    quantity REAL,
    price REAL,
    commission REAL DEFAULT 0,
    notes TEXT,
    metadata JSON, -- Additional context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE SET NULL,
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE SET NULL
);

-- ==================== Create Indexes ====================

-- Portfolio indexes
CREATE INDEX IF NOT EXISTS idx_portfolios_type ON portfolios(portfolio_type);
CREATE INDEX IF NOT EXISTS idx_portfolios_archived ON portfolios(user_id, is_archived);
CREATE INDEX IF NOT EXISTS idx_portfolios_risk_tolerance ON portfolios(risk_tolerance);

-- Holdings indexes
CREATE INDEX IF NOT EXISTS idx_holdings_current_price ON holdings(portfolio_id, current_price);
CREATE INDEX IF NOT EXISTS idx_holdings_unrealized_gain ON holdings(portfolio_id, unrealized_gain_loss);
CREATE INDEX IF NOT EXISTS idx_holdings_sector ON holdings(portfolio_id, sector);
CREATE INDEX IF NOT EXISTS idx_holdings_closed ON holdings(portfolio_id, is_closed);
CREATE INDEX IF NOT EXISTS idx_holdings_target_price ON holdings(portfolio_id, target_price);

-- Watchlist indexes
CREATE INDEX IF NOT EXISTS idx_watchlists_archived ON watchlists(user_id, is_archived);
CREATE INDEX IF NOT EXISTS idx_watchlists_sort_order ON watchlists(user_id, sort_order);

-- Watchlist items indexes
CREATE INDEX IF NOT EXISTS idx_watchlist_items_target_price ON watchlist_items(watchlist_id, target_price);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_earnings_date ON watchlist_items(watchlist_id, earnings_date);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_sector ON watchlist_items(watchlist_id, sector);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_analyst_rating ON watchlist_items(watchlist_id, analyst_rating);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_portfolio_performance_date ON portfolio_performance(portfolio_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_watchlist_performance_date ON watchlist_performance(watchlist_id, snapshot_date DESC);

-- Trading activity indexes
CREATE INDEX IF NOT EXISTS idx_trading_activity_user ON trading_activity(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trading_activity_portfolio ON trading_activity(portfolio_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trading_activity_symbol ON trading_activity(stock_symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trading_activity_type ON trading_activity(activity_type, created_at DESC);

