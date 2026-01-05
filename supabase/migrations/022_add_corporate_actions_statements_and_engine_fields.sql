-- Add corporate actions, earnings, and financial statements tables used by the Python worker

-- Corporate actions (dividends/splits) keyed by stock_symbol
CREATE TABLE IF NOT EXISTS corporate_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_symbol TEXT NOT NULL,
    action_date DATE NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('dividend', 'split')),
    value DOUBLE PRECISION,
    source TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (stock_symbol, action_date, action_type)
);

CREATE INDEX IF NOT EXISTS idx_corporate_actions_symbol_date
ON corporate_actions(stock_symbol, action_date DESC);

-- Earnings events keyed by stock_symbol
CREATE TABLE IF NOT EXISTS earnings_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    earnings_id TEXT,
    stock_symbol TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    eps_estimate DOUBLE PRECISION,
    eps_actual DOUBLE PRECISION,
    revenue_estimate BIGINT,
    revenue_actual BIGINT,
    surprise_percentage DOUBLE PRECISION,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (stock_symbol, earnings_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_data_symbol_date
ON earnings_data(stock_symbol, earnings_date DESC);

CREATE INDEX IF NOT EXISTS idx_earnings_data_date
ON earnings_data(earnings_date DESC);

-- Financial statements as normalized JSON snapshots (income/balance/cashflow) keyed by stock_symbol
CREATE TABLE IF NOT EXISTS financial_statements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_symbol TEXT NOT NULL,
    period_type TEXT NOT NULL CHECK (period_type IN ('quarterly', 'annual')),
    statement_type TEXT NOT NULL CHECK (statement_type IN ('income_statement', 'balance_sheet', 'cash_flow')),
    fiscal_period DATE NOT NULL,
    source TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (stock_symbol, period_type, statement_type, fiscal_period)
);

CREATE INDEX IF NOT EXISTS idx_financial_statements_symbol_period
ON financial_statements(stock_symbol, fiscal_period DESC);

-- Extend indicators_daily to support swing_regime_engine inputs
ALTER TABLE IF EXISTS indicators_daily
    ADD COLUMN IF NOT EXISTS atr DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS bb_width DOUBLE PRECISION;
