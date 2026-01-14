-- ========================================
-- PORTFOLIO MANAGEMENT DATABASE SCHEMA
-- Industry-standard portfolio management with audit trails
-- ========================================

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'premium')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

-- Portfolios table (users can have multiple portfolios)
CREATE TABLE portfolios (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    portfolio_type VARCHAR(20) DEFAULT 'custom' CHECK (portfolio_type IN ('custom', 'growth', 'income', 'balanced', 'retirement')),
    initial_capital DECIMAL(15,2) DEFAULT 10000.00,
    currency VARCHAR(3) DEFAULT 'USD',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, name)
);

-- Portfolio holdings table
CREATE TABLE portfolio_holdings (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    asset_type VARCHAR(20) NOT NULL CHECK (asset_type IN ('stock', 'regular_etf', '3x_etf', 'crypto', 'bond')),
    shares_held DECIMAL(15,4) DEFAULT 0,
    average_cost DECIMAL(10,2) DEFAULT 0,
    first_purchase_date DATE,
    last_purchase_date DATE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'sold')),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(portfolio_id, symbol)
);

-- Symbol master table (audit trail for all symbols ever analyzed)
CREATE TABLE symbol_master (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    company_name VARCHAR(255),
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap BIGINT,
    country VARCHAR(50),
    currency VARCHAR(3),
    exchange VARCHAR(10),
    asset_type VARCHAR(20),
    is_active BOOLEAN DEFAULT true,
    first_analyzed DATE,
    last_analyzed DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Signal history table (complete audit trail of all signals generated)
CREATE TABLE signal_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL REFERENCES symbol_master(symbol),
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE SET NULL,  -- NULL if not portfolio-specific
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,  -- NULL if system-generated
    
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
    reasoning JSONB,  -- Array of reasoning strings
    
    -- Performance tracking
    target_price DECIMAL(10,2),  -- Expected target price
    stop_loss DECIMAL(10,2),     -- Stop loss price
    time_horizon INTEGER,        -- Days expected to hold
    actual_outcome VARCHAR(20),   -- 'profit', 'loss', 'breakeven', 'pending'
    actual_return DECIMAL(8,4),   -- Actual return percentage
    days_held INTEGER,           -- Actual days held
    
    signal_date DATE NOT NULL,
    signal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for performance
    INDEX idx_signal_symbol_date (symbol, signal_date),
    INDEX idx_signal_portfolio_date (portfolio_id, signal_date),
    INDEX idx_signal_user_date (user_id, signal_date),
    INDEX idx_signal_type_date (signal_type, signal_date)
);

-- Portfolio performance snapshots (daily portfolio value tracking)
CREATE TABLE portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
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
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(portfolio_id, snapshot_date),
    INDEX idx_portfolio_snapshot_date (portfolio_id, snapshot_date)
);

-- Scheduled analyses table
CREATE TABLE scheduled_analyses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE CASCADE,
    
    schedule_type VARCHAR(20) NOT NULL CHECK (schedule_type IN ('daily', 'weekly', 'monthly')),
    schedule_time TIME NOT NULL,  -- Time of day to run
    schedule_day INTEGER,         -- Day of week (1-7) for weekly, day of month (1-31) for monthly
    is_active BOOLEAN DEFAULT true,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    
    notification_preferences JSONB DEFAULT '{"email": true, "push": false}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analysis logs table (audit trail for all analysis runs)
CREATE TABLE analysis_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    portfolio_id INTEGER REFERENCES portfolios(id) ON DELETE SET NULL,
    
    analysis_type VARCHAR(20) NOT NULL CHECK (analysis_type IN ('single', 'portfolio', 'backtest')),
    symbols_analyzed INTEGER DEFAULT 0,
    signals_generated INTEGER DEFAULT 0,
    success_rate DECIMAL(5,2),
    
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_ms INTEGER,  -- Duration in milliseconds
    
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_message TEXT,
    
    metadata JSONB,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_analysis_user_date (user_id, created_at),
    INDEX idx_analysis_portfolio_date (portfolio_id, created_at)
);

-- User preferences table
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    
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
    default_portfolio_id INTEGER REFERENCES portfolios(id),
    theme VARCHAR(20) DEFAULT 'light',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id)
);

-- Create default admin user
INSERT INTO users (username, email, password_hash, full_name, role) 
VALUES ('admin', 'admin@trading-system.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6QJw/2Ej7W', 'System Administrator', 'admin');

-- Create default portfolio for admin
INSERT INTO portfolios (user_id, name, description, portfolio_type, initial_capital)
SELECT id, 'Default Portfolio', 'Default portfolio for admin user', 'balanced', 10000.00
FROM users WHERE username = 'admin';

-- Create indexes for better performance
CREATE INDEX idx_symbol_master_symbol ON symbol_master(symbol);
CREATE INDEX idx_symbol_master_active ON symbol_master(is_active);
CREATE INDEX idx_portfolios_user_active ON portfolios(user_id, is_active);
CREATE INDEX idx_holdings_portfolio_symbol ON portfolio_holdings(portfolio_id, symbol);
CREATE INDEX idx_holdings_active ON portfolio_holdings(status);

-- Create trigger to update updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to tables with updated_at columns
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_portfolios_updated_at BEFORE UPDATE ON portfolios FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_holdings_updated_at BEFORE UPDATE ON portfolio_holdings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_symbol_master_updated_at BEFORE UPDATE ON symbol_master FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_scheduled_analyses_updated_at BEFORE UPDATE ON scheduled_analyses FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_user_preferences_updated_at BEFORE UPDATE ON user_preferences FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
