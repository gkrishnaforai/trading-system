-- ========================================
-- PORTFOLIO MANAGEMENT DATABASE SCHEMA (COMPATIBLE VERSION)
-- Compatible with existing UUID-based tables
-- ========================================

-- Check if users table needs portfolio columns
DO $$
BEGIN
    -- Add portfolio-specific columns to users table if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'password_hash') THEN
        ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'role') THEN
        ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'premium'));
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'full_name') THEN
        ALTER TABLE users ADD COLUMN full_name VARCHAR(100);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'is_active') THEN
        ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT true;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_login') THEN
        ALTER TABLE users ADD COLUMN last_login TIMESTAMP;
    END IF;
END $$;

-- Check if portfolios table needs columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolios' AND column_name = 'description') THEN
        ALTER TABLE portfolios ADD COLUMN description TEXT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolios' AND column_name = 'portfolio_type') THEN
        ALTER TABLE portfolios ADD COLUMN portfolio_type VARCHAR(20) DEFAULT 'custom' CHECK (portfolio_type IN ('custom', 'growth', 'income', 'balanced', 'retirement'));
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolios' AND column_name = 'initial_capital') THEN
        ALTER TABLE portfolios ADD COLUMN initial_capital DECIMAL(15,2) DEFAULT 10000.00;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolios' AND column_name = 'currency') THEN
        ALTER TABLE portfolios ADD COLUMN currency VARCHAR(3) DEFAULT 'USD';
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'portfolios' AND column_name = 'is_active') THEN
        ALTER TABLE portfolios ADD COLUMN is_active BOOLEAN DEFAULT true;
    END IF;
END $$;

-- Portfolio holdings table (compatible with UUID portfolio_id)
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE CASCADE,
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
CREATE TABLE IF NOT EXISTS symbol_master (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
CREATE TABLE IF NOT EXISTS signal_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES symbol_master(symbol),
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Portfolio performance snapshots (daily portfolio value tracking)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE CASCADE,
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
    
    UNIQUE(portfolio_id, snapshot_date)
);

-- Scheduled analyses table
CREATE TABLE IF NOT EXISTS scheduled_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE CASCADE,
    
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
CREATE TABLE IF NOT EXISTS analysis_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE SET NULL,
    
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
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User preferences table
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    
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
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id)
);

-- Create or update admin user
INSERT INTO users (username, email, password_hash, full_name, role) 
VALUES ('admin', 'admin@trading-system.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6QJw/2Ej7W', 'System Administrator', 'admin')
ON CONFLICT (username) DO UPDATE SET
    password_hash = EXCLUDED.password_hash,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role;

-- Create default portfolio for admin if it doesn't exist
INSERT INTO portfolios (user_id, name, description, portfolio_type, initial_capital)
SELECT u.id, 'Default Portfolio', 'Default portfolio for admin user', 'balanced', 10000.00
FROM users u WHERE u.username = 'admin' AND NOT EXISTS (
    SELECT 1 FROM portfolios p WHERE p.user_id = u.id AND p.name = 'Default Portfolio'
);

-- Create indexes for better performance (only after tables exist)
DO $$
BEGIN
    -- Symbol master indexes
    CREATE INDEX IF NOT EXISTS idx_symbol_master_symbol ON symbol_master(symbol);
    CREATE INDEX IF NOT EXISTS idx_symbol_master_active ON symbol_master(is_active);
    
    -- Portfolios indexes
    CREATE INDEX IF NOT EXISTS idx_portfolios_user_active ON portfolios(user_id, is_active);
    
    -- Holdings indexes
    CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_symbol ON portfolio_holdings(portfolio_id, symbol);
    CREATE INDEX IF NOT EXISTS idx_holdings_active ON portfolio_holdings(status);
    
    -- Signal history indexes
    CREATE INDEX IF NOT EXISTS idx_signal_symbol_date ON signal_history(symbol, signal_date);
    CREATE INDEX IF NOT EXISTS idx_signal_portfolio_date ON signal_history(portfolio_id, signal_date);
    CREATE INDEX IF NOT EXISTS idx_signal_user_date ON signal_history(user_id, signal_date);
    CREATE INDEX IF NOT EXISTS idx_signal_type_date ON signal_history(signal_type, signal_date);
    
    -- Portfolio snapshots index
    CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_date ON portfolio_snapshots(portfolio_id, snapshot_date);
    
    -- Analysis logs indexes
    CREATE INDEX IF NOT EXISTS idx_analysis_user_date ON analysis_logs(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_analysis_portfolio_date ON analysis_logs(portfolio_id, created_at);
END $$;

-- Create trigger to update updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to tables with updated_at columns
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_portfolios_updated_at ON portfolios;
CREATE TRIGGER update_portfolios_updated_at BEFORE UPDATE ON portfolios FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_holdings_updated_at ON portfolio_holdings;
CREATE TRIGGER update_holdings_updated_at BEFORE UPDATE ON portfolio_holdings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_symbol_master_updated_at ON symbol_master;
CREATE TRIGGER update_symbol_master_updated_at BEFORE UPDATE ON symbol_master FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_scheduled_analyses_updated_at ON scheduled_analyses;
CREATE TRIGGER update_scheduled_analyses_updated_at BEFORE UPDATE ON scheduled_analyses FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER update_user_preferences_updated_at BEFORE UPDATE ON user_preferences FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
