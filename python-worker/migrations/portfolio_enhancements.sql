-- ========================================
-- PORTFOLIO MANAGEMENT ENHANCEMENTS
-- Add portfolio management features to existing tables
-- ========================================

-- Add portfolio management columns to existing users table
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

-- Add portfolio management columns to existing portfolios table
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

-- Create portfolio_holdings table
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

-- Add portfolio management columns to existing signal_history table
DO $$
BEGIN
    -- Add new columns to signal_history if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'portfolio_id') THEN
        ALTER TABLE signal_history ADD COLUMN portfolio_id UUID REFERENCES portfolios(id) ON DELETE SET NULL;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'user_id') THEN
        ALTER TABLE signal_history ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'signal_type') THEN
        ALTER TABLE signal_history ADD COLUMN signal_type VARCHAR(10) NOT NULL DEFAULT 'HOLD' CHECK (signal_type IN ('BUY', 'SELL', 'HOLD'));
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'confidence') THEN
        ALTER TABLE signal_history ADD COLUMN confidence DECIMAL(5,2) CHECK (confidence >= 0 AND confidence <= 100);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'price') THEN
        ALTER TABLE signal_history ADD COLUMN price DECIMAL(10,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'rsi') THEN
        ALTER TABLE signal_history ADD COLUMN rsi DECIMAL(5,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'macd') THEN
        ALTER TABLE signal_history ADD COLUMN macd DECIMAL(10,4);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'macd_signal') THEN
        ALTER TABLE signal_history ADD COLUMN macd_signal DECIMAL(10,4);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'sma_20') THEN
        ALTER TABLE signal_history ADD COLUMN sma_20 DECIMAL(10,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'sma_50') THEN
        ALTER TABLE signal_history ADD COLUMN sma_50 DECIMAL(10,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'ema_20') THEN
        ALTER TABLE signal_history ADD COLUMN ema_20 DECIMAL(10,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'volume') THEN
        ALTER TABLE signal_history ADD COLUMN volume BIGINT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'ema_slope') THEN
        ALTER TABLE signal_history ADD COLUMN ema_slope DECIMAL(8,6);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'volatility') THEN
        ALTER TABLE signal_history ADD COLUMN volatility DECIMAL(5,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'vix_level') THEN
        ALTER TABLE signal_history ADD COLUMN vix_level DECIMAL(5,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'recent_change') THEN
        ALTER TABLE signal_history ADD COLUMN recent_change DECIMAL(5,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'fear_greed_state') THEN
        ALTER TABLE signal_history ADD COLUMN fear_greed_state VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'fear_greed_bias') THEN
        ALTER TABLE signal_history ADD COLUMN fear_greed_bias VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'recovery_detected') THEN
        ALTER TABLE signal_history ADD COLUMN recovery_detected BOOLEAN;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'engine_type') THEN
        ALTER TABLE signal_history ADD COLUMN engine_type VARCHAR(50);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'asset_type') THEN
        ALTER TABLE signal_history ADD COLUMN asset_type VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'strategy') THEN
        ALTER TABLE signal_history ADD COLUMN strategy VARCHAR(50);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'target_price') THEN
        ALTER TABLE signal_history ADD COLUMN target_price DECIMAL(10,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'stop_loss') THEN
        ALTER TABLE signal_history ADD COLUMN stop_loss DECIMAL(10,2);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'time_horizon') THEN
        ALTER TABLE signal_history ADD COLUMN time_horizon INTEGER;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'actual_outcome') THEN
        ALTER TABLE signal_history ADD COLUMN actual_outcome VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'actual_return') THEN
        ALTER TABLE signal_history ADD COLUMN actual_return DECIMAL(8,4);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'days_held') THEN
        ALTER TABLE signal_history ADD COLUMN days_held INTEGER;
    END IF;
    
    -- Add signal_date column if it doesn't exist (for compatibility)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'signal_date') THEN
        ALTER TABLE signal_history ADD COLUMN signal_date DATE;
        
        -- Populate signal_date from analysis_date for existing records
        UPDATE signal_history SET signal_date = analysis_date WHERE signal_date IS NULL AND analysis_date IS NOT NULL;
    END IF;
    
    -- Add signal_time column if it doesn't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'signal_time') THEN
        ALTER TABLE signal_history ADD COLUMN signal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        
        -- Populate signal_time from timestamp for existing records
        UPDATE signal_history SET signal_time = timestamp WHERE signal_time IS NULL AND timestamp IS NOT NULL;
    END IF;
END $$;

-- Add portfolio management columns to existing symbol_master table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'company_name') THEN
        ALTER TABLE symbol_master ADD COLUMN company_name VARCHAR(255);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'sector') THEN
        ALTER TABLE symbol_master ADD COLUMN sector VARCHAR(100);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'industry') THEN
        ALTER TABLE symbol_master ADD COLUMN industry VARCHAR(100);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'market_cap') THEN
        ALTER TABLE symbol_master ADD COLUMN market_cap BIGINT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'country') THEN
        ALTER TABLE symbol_master ADD COLUMN country VARCHAR(50);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'currency') THEN
        ALTER TABLE symbol_master ADD COLUMN currency VARCHAR(3);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'exchange') THEN
        ALTER TABLE symbol_master ADD COLUMN exchange VARCHAR(10);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'asset_type') THEN
        ALTER TABLE symbol_master ADD COLUMN asset_type VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'is_active') THEN
        ALTER TABLE symbol_master ADD COLUMN is_active BOOLEAN DEFAULT true;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'first_analyzed') THEN
        ALTER TABLE symbol_master ADD COLUMN first_analyzed DATE;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'last_analyzed') THEN
        ALTER TABLE symbol_master ADD COLUMN last_analyzed DATE;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'symbol_master' AND column_name = 'updated_at') THEN
        ALTER TABLE symbol_master ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
    END IF;
END $$;

-- Create additional portfolio management tables
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

CREATE TABLE IF NOT EXISTS scheduled_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE CASCADE,
    
    schedule_type VARCHAR(20) NOT NULL CHECK (schedule_type IN ('daily', 'weekly', 'monthly')),
    schedule_time TIME NOT NULL,
    schedule_day INTEGER,
    is_active BOOLEAN DEFAULT true,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    
    notification_preferences JSONB DEFAULT '{"email": true, "push": false}',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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
    duration_ms INTEGER,
    
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_message TEXT,
    
    metadata JSONB,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_symbol_master_symbol ON symbol_master(symbol);
CREATE INDEX IF NOT EXISTS idx_symbol_master_active ON symbol_master(is_active);
CREATE INDEX IF NOT EXISTS idx_portfolios_user_active ON portfolios(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_symbol ON portfolio_holdings(portfolio_id, symbol);
CREATE INDEX IF NOT EXISTS idx_holdings_active ON portfolio_holdings(status);

-- Signal history indexes (only if columns exist)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'signal_date') THEN
        CREATE INDEX IF NOT EXISTS idx_signal_symbol_date ON signal_history(symbol, signal_date);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'portfolio_id') THEN
        CREATE INDEX IF NOT EXISTS idx_signal_portfolio_date ON signal_history(portfolio_id, signal_date);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'user_id') THEN
        CREATE INDEX IF NOT EXISTS idx_signal_user_date ON signal_history(user_id, signal_date);
    END IF;
    
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_history' AND column_name = 'signal_type') THEN
        CREATE INDEX IF NOT EXISTS idx_signal_type_date ON signal_history(signal_type, signal_date);
    END IF;
END $$;

-- Portfolio snapshots index
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_date ON portfolio_snapshots(portfolio_id, snapshot_date);

-- Analysis logs indexes
CREATE INDEX IF NOT EXISTS idx_analysis_user_date ON analysis_logs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_analysis_portfolio_date ON analysis_logs(portfolio_id, created_at);

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
