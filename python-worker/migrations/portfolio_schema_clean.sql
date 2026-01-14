-- ========================================
-- CLEAN PORTFOLIO SCHEMA MIGRATION
-- Handles existing tables and creates proper relationships
-- ========================================

-- Step 1: Drop existing problematic portfolio tables if they exist
DROP TABLE IF EXISTS portfolio_holdings CASCADE;
DROP TABLE IF EXISTS portfolios CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS symbol_master CASCADE;

-- Step 2: Create new tables with proper UUID and relationships
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
CREATE TABLE portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE RESTRICT,
    asset_type VARCHAR(20) NOT NULL CHECK (asset_type IN ('stock', 'regular_etf', '3x_etf', 'crypto', 'bond')),
    shares_held DECIMAL(15,4) DEFAULT 0,
    average_cost DECIMAL(10,2) DEFAULT 0,
    first_purchase_date DATE,
    last_purchase_date DATE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'sold')),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(portfolio_id, symbol)
);

-- Step 3: Create indexes for performance
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_active ON users(is_active);
CREATE INDEX idx_portfolios_user_id ON portfolios(user_id);
CREATE INDEX idx_portfolios_user_active ON portfolios(user_id, is_active);
CREATE INDEX idx_holdings_portfolio_id ON portfolio_holdings(portfolio_id);
CREATE INDEX idx_holdings_symbol ON portfolio_holdings(symbol);
CREATE INDEX idx_holdings_portfolio_symbol ON portfolio_holdings(portfolio_id, symbol);
CREATE INDEX idx_holdings_status ON portfolio_holdings(status);

-- Step 4: Create views for common queries
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
    -- Calculated values
    (ph.shares_held * ph.average_cost) as total_cost
FROM portfolio_holdings ph
INNER JOIN stocks s ON ph.symbol = s.symbol;

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

-- Step 5: Create triggers for updated_at columns
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

-- Step 6: Create validation function for stock symbols
CREATE OR REPLACE FUNCTION validate_stock_symbol()
RETURNS TRIGGER AS $$
BEGIN
    -- Ensure stock exists and is active
    IF NOT EXISTS (SELECT 1 FROM stocks WHERE symbol = NEW.symbol AND is_active = TRUE) THEN
        RAISE EXCEPTION 'Stock symbol % does not exist or is not active', NEW.symbol;
    END IF;
    
    -- Set asset_type based on stock data if not specified
    IF NEW.asset_type IS NULL OR NEW.asset_type = '' THEN
        NEW.asset_type = 'stock';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER validate_portfolio_holding
BEFORE INSERT OR UPDATE ON portfolio_holdings
FOR EACH ROW EXECUTE FUNCTION validate_stock_symbol();

-- Step 7: Create default admin user
INSERT INTO users (username, email, password_hash, full_name, role) 
VALUES ('admin', 'admin@trading-system.local', 'admin123', 'System Administrator', 'admin');

-- Step 8: Create default portfolio for admin
INSERT INTO portfolios (user_id, name, description, portfolio_type, initial_capital)
SELECT id, 'Default Portfolio', 'Default portfolio for admin user', 'balanced', 10000.00
FROM users WHERE username = 'admin';

-- Step 9: Add comments
COMMENT ON TABLE portfolio_holdings IS 'Junction table between portfolios and stocks - stores position information';
COMMENT ON TABLE portfolio_holdings_enriched IS 'Portfolio holdings enriched with stock information from master stocks table';
COMMENT ON TABLE portfolio_summary IS 'Portfolio summary with holdings count and total invested amount';
COMMENT ON COLUMN portfolio_holdings.symbol IS 'Foreign key reference to stocks.symbol - ensures data integrity';
