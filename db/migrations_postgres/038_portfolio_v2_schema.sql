-- advisory-only: schema for the portfolio cockpit; nothing here trades
-- Evolves baseline users/portfolios to the v2 model the API actually uses
-- and creates portfolio_holdings + summary/enriched views.
-- Pure DDL only — the migration runner splits on ';', so no functions,
-- triggers, or DO blocks. updated_at is maintained in the API layer
-- (PUT already sets CURRENT_TIMESTAMP).
-- Idempotent + additive: safe on baseline-only and partially migrated DBs.

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;

ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS portfolio_type VARCHAR(20) NOT NULL DEFAULT 'custom';
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS initial_capital NUMERIC(15,2) NOT NULL DEFAULT 10000;
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS currency VARCHAR(5);
ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE portfolios SET currency = 'USD' WHERE currency IS NULL;

CREATE TABLE IF NOT EXISTS portfolio_holdings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE RESTRICT,
  asset_type VARCHAR(20) NOT NULL DEFAULT 'stock'
    CHECK (asset_type IN ('stock', 'regular_etf', '3x_etf', 'crypto', 'bond')),
  shares_held NUMERIC(15,4) NOT NULL DEFAULT 0,
  average_cost NUMERIC(15,4) NOT NULL DEFAULT 0,
  first_purchase_date DATE,
  last_purchase_date DATE,
  status VARCHAR(20) NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'inactive', 'sold')),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (portfolio_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_portfolios_user_active_v2
  ON portfolios(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_holdings_portfolio_id
  ON portfolio_holdings(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol
  ON portfolio_holdings(symbol);
CREATE INDEX IF NOT EXISTS idx_holdings_status
  ON portfolio_holdings(status);

CREATE OR REPLACE VIEW portfolio_holdings_enriched AS
SELECT
  ph.id, ph.portfolio_id, ph.symbol, ph.asset_type, ph.shares_held,
  ph.average_cost, ph.status, ph.created_at, ph.updated_at, ph.notes,
  s.company_name, s.exchange, s.sector, s.industry, s.market_cap,
  s.country, s.currency AS stock_currency,
  s.is_active AS stock_is_active,
  (ph.shares_held * ph.average_cost) AS total_cost
FROM portfolio_holdings ph
INNER JOIN stocks s ON ph.symbol = s.symbol;

CREATE OR REPLACE VIEW portfolio_summary AS
SELECT
  p.id, p.user_id, p.name, p.description, p.portfolio_type,
  p.initial_capital, p.currency, p.is_active, p.created_at, p.updated_at,
  COUNT(ph.id) AS holdings_count,
  COALESCE(SUM(ph.shares_held * ph.average_cost), 0) AS total_invested
FROM portfolios p
LEFT JOIN portfolio_holdings ph
  ON p.id = ph.portfolio_id AND ph.status = 'active'
GROUP BY
  p.id, p.user_id, p.name, p.description, p.portfolio_type,
  p.initial_capital, p.currency, p.is_active, p.created_at, p.updated_at;
