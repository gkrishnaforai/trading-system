-- ========================================
-- INDUSTRY STANDARD PORTFOLIO MANAGEMENT SCHEMA
-- Clean design with stocks table as single source of truth
-- ========================================

-- Drop existing portfolio tables if they exist (for clean start)
DROP TABLE IF EXISTS portfolio_holdings CASCADE;
DROP TABLE IF EXISTS portfolios CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS symbol_master CASCADE;  -- Not needed with stocks table as master

-- Users table (UUID for modern standards)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'premium')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- Portfolios table (UUID for consistency)
CREATE TABLE portfolios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    portfolio_type VARCHAR(20) DEFAULT 'custom' CHECK (portfolio_type IN ('custom', 'growth', 'income', 'balanced', 'retirement')),
    initial_capital DECIMAL(15,2) DEFAULT 10000.00,
    currency VARCHAR(3) DEFAULT 'USD',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, name)
);

-- Portfolio Holdings table (many-to-many relationship)
-- This is the junction table between portfolios and stocks
CREATE TABLE portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE RESTRICT,  -- FK to stocks table
    asset_type VARCHAR(20) NOT NULL CHECK (asset_type IN ('stock', 'regular_etf', '3x_etf', 'crypto', 'bond')),
    shares_held DECIMAL(15,4) DEFAULT 0,
    average_cost DECIMAL(10,2) DEFAULT 0,
    first_purchase_date DATE,
    last_purchase_date DATE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'sold')),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(portfolio_id, symbol)  -- One holding per symbol per portfolio
);

-- Portfolio Performance Snapshots (daily tracking)
CREATE TABLE portfolio_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    total_value DECIMAL(15,2) NOT NULL,
    cash_balance DECIMAL(15,2) DEFAULT 0,
    invested_value DECIMAL(15,2) DEFAULT 0,
    daily_return DECIMAL(8,4),
    daily_return_pct DECIMAL(5,2),
    total_return DECIMAL(8,4),
    total_return_pct DECIMAL(5,2),
    
    -- Market conditions
    vix_level DECIMAL(5,2),
    market_sentiment VARCHAR(20),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(portfolio_id, snapshot_date)
);

-- Signal History (audit trail for all signals)
CREATE TABLE signal_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE SET NULL,  -- NULL if not portfolio-specific
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,  -- NULL if system-generated
    
    -- Signal details
    signal_type VARCHAR(10) NOT NULL CHECK (signal_type IN ('BUY', 'SELL', 'HOLD')),
    confidence DECIMAL(5,2) NOT NULL CHECK (confidence >= 0 AND confidence <= 100),
    
    -- Market data at time of signal
    price DECIMAL(10,2) NOT NULL,
    rsi DECIMAL(5,2),
    macd DECIMAL(10,4),
    macd_signal DECIMAL(10,4),
    sma_20 DECIMAL(10,2),
    sma_50 DECIMAL(10,2),
    ema_20 DECIMAL(10,2),
    volume BIGINT,
    
    -- Analysis data
    ema_slope DECIMAL(8,6),
    volatility DECIMAL(5,2),
    vix_level DECIMAL(5,2),
    recent_change DECIMAL(5,2),
    
    -- Market context
    fear_greed_state VARCHAR(20),
    fear_greed_bias VARCHAR(20),
    recovery_detected BOOLEAN,
    
    -- Metadata
    engine_type VARCHAR(50),
    asset_type VARCHAR(20),
    strategy VARCHAR(50),
    reasoning JSONB,
    
    -- Performance tracking
    target_price DECIMAL(10,2),
    stop_loss DECIMAL(10,2),
    time_horizon INTEGER,
    actual_outcome VARCHAR(20),
    actual_return DECIMAL(8,4),
    days_held INTEGER,
    
    signal_date DATE NOT NULL,
    signal_time TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Scheduled Analyses
CREATE TABLE scheduled_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    
    schedule_type VARCHAR(20) NOT NULL CHECK (schedule_type IN ('daily', 'weekly', 'monthly')),
    schedule_time TIME NOT NULL,
    schedule_day INTEGER,
    is_active BOOLEAN DEFAULT true,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    
    notification_preferences JSONB DEFAULT '{"email": true, "push": false}',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Analysis Logs
CREATE TABLE analysis_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE SET NULL,
    
    analysis_type VARCHAR(20) NOT NULL CHECK (analysis_type IN ('single', 'portfolio', 'backtest')),
    symbols_analyzed INTEGER DEFAULT 0,
    signals_generated INTEGER DEFAULT 0,
    success_rate DECIMAL(5,2),
    
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_ms INTEGER,
    
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_message TEXT,
    
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User Preferences
CREATE TABLE user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Analysis preferences
    default_confidence_threshold DECIMAL(5,2) DEFAULT 60.0,
    default_time_horizon INTEGER DEFAULT 5,
    risk_tolerance VARCHAR(20) DEFAULT 'moderate' CHECK (risk_tolerance IN ('conservative', 'moderate', 'aggressive')),
    
    -- Notification preferences
    email_notifications BOOLEAN DEFAULT true,
    push_notifications BOOLEAN DEFAULT false,
    signal_alerts BOOLEAN DEFAULT true,
    portfolio_alerts BOOLEAN DEFAULT true,
    
    -- UI preferences
    default_portfolio_id UUID REFERENCES portfolios(id),
    theme VARCHAR(20) DEFAULT 'light',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- ========================================
-- INDEXES FOR PERFORMANCE
-- ========================================

-- Users
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active);

-- Portfolios
CREATE INDEX idx_portfolios_user_id ON portfolios(user_id);
CREATE INDEX idx_portfolios_user_active ON portfolios(user_id, is_active);

-- Portfolio Holdings (critical for performance)
CREATE INDEX idx_holdings_portfolio_id ON portfolio_holdings(portfolio_id);
CREATE INDEX idx_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX idx_holdings_portfolio_symbol ON portfolio_holdings(portfolio_id, symbol);
CREATE INDEX idx_holdings_status ON portfolio_holdings(status);

-- Portfolio Snapshots
CREATE INDEX idx_snapshots_portfolio_id ON portfolio_snapshots(portfolio_id);
CREATE INDEX idx_snapshots_portfolio_date ON portfolio_snapshots(portfolio_id, snapshot_date);

-- Signal History
CREATE INDEX idx_signal_symbol_date ON signal_history(symbol, signal_date);
CREATE INDEX idx_signal_portfolio_date ON signal_history(portfolio_id, signal_date);
CREATE INDEX idx_signal_user_date ON signal_history(user_id, signal_date);
CREATE INDEX idx_signal_type_date ON signal_history(signal_type, signal_date);

-- Analysis Logs
CREATE INDEX idx_analysis_user_date ON analysis_logs(user_id, created_at);
CREATE INDEX idx_analysis_portfolio_date ON analysis_logs(portfolio_id, created_at);

-- ========================================
-- VIEWS FOR COMMON QUERIES
-- ========================================

-- Enriched Portfolio Holdings (joins with stocks table)
CREATE VIEW portfolio_holdings_enriched AS
SELECT 
    ph.id,
    ph.portfolio_id,
    ph.symbol,
    ph.asset_type,
    ph.shares_held,
    ph.average_cost,
    ph.status,
    ph.created_at,
    ph.updated_at,
    ph.notes,
    -- Stock information from master stocks table
    s.company_name,
    s.exchange,
    s.sector,
    s.industry,
    s.market_cap,
    s.country,
    s.currency as stock_currency,
    s.is_active as stock_is_active,
    -- Data completeness flags
    s.has_fundamentals,
    s.has_earnings,
    s.has_market_data,
    s.has_indicators,
    -- Calculated values
    (ph.shares_held * ph.average_cost) as total_cost
FROM portfolio_holdings ph
INNER JOIN stocks s ON ph.symbol = s.symbol;

-- Portfolio Summary with Holdings Count
CREATE VIEW portfolio_summary AS
SELECT 
    p.id,
    p.user_id,
    p.name,
    p.description,
    p.portfolio_type,
    p.initial_capital,
    p.currency,
    p.is_active,
    p.created_at,
    p.updated_at,
    COUNT(ph.id) as holdings_count,
    COALESCE(SUM(ph.shares_held * ph.average_cost), 0) as total_invested
FROM portfolios p
LEFT JOIN portfolio_holdings ph ON p.id = ph.portfolio_id AND ph.status = 'active'
GROUP BY p.id, p.user_id, p.name, p.description, p.portfolio_type, 
         p.initial_capital, p.currency, p.is_active, p.created_at, p.updated_at;

-- ========================================
-- TRIGGERS AND FUNCTIONS
-- ========================================

-- Update updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_portfolios_updated_at BEFORE UPDATE ON portfolios FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_holdings_updated_at BEFORE UPDATE ON portfolio_holdings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_scheduled_analyses_updated_at BEFORE UPDATE ON scheduled_analyses FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_preferences_updated_at BEFORE UPDATE ON user_preferences FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Validate stock symbol before adding to portfolio
CREATE OR REPLACE FUNCTION validate_stock_symbol()
RETURNS TRIGGER AS $$
BEGIN
    -- Ensure stock exists and is active
    IF NOT EXISTS (SELECT 1 FROM stocks WHERE symbol = NEW.symbol AND is_active = TRUE) THEN
        RAISE EXCEPTION 'Stock symbol % does not exist or is not active', NEW.symbol;
    END IF;
    
    -- Set asset_type based on stock data if not specified
    IF NEW.asset_type IS NULL OR NEW.asset_type = '' THEN
        NEW.asset_type = 'stock';  -- Default to stock
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_portfolio_holding
BEFORE INSERT OR UPDATE ON portfolio_holdings
FOR EACH ROW EXECUTE FUNCTION validate_stock_symbol();

-- ========================================
-- DEFAULT DATA
-- ========================================

-- Create default admin user (password: admin123 in plain text for now)
INSERT INTO users (username, email, password_hash, full_name, role) 
VALUES ('admin', 'admin@trading-system.local', 'admin123', 'System Administrator', 'admin');

-- Create default portfolio for admin
INSERT INTO portfolios (user_id, name, description, portfolio_type, initial_capital)
SELECT id, 'Default Portfolio', 'Default portfolio for admin user', 'balanced', 10000.00
FROM users WHERE username = 'admin';

-- ========================================
-- COMMENTS
-- ========================================

COMMENT ON TABLE portfolio_holdings IS 'Junction table between portfolios and stocks - stores position information';
COMMENT ON TABLE portfolio_holdings_enriched IS 'Portfolio holdings enriched with stock information from master stocks table';
COMMENT ON TABLE portfolio_summary IS 'Portfolio summary with holdings count and total invested amount';
COMMENT ON COLUMN portfolio_holdings.symbol IS 'Foreign key reference to stocks.symbol - ensures data integrity';
COMMENT ON CONSTRAINT portfolio_holdings_symbol_fkey IS 'Ensures only valid stock symbols can be added to portfolios';
