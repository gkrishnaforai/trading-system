-- Point-in-time analyst estimate history for fundamental momentum.
CREATE TABLE IF NOT EXISTS fundamental_estimate_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(32) NOT NULL,
    as_of_date DATE NOT NULL,
    fiscal_period VARCHAR(32) NOT NULL,
    fiscal_year INTEGER NOT NULL,
    eps_estimate NUMERIC(20,8),
    revenue_estimate NUMERIC(20,8),
    eps_growth_estimate NUMERIC(12,8),
    revenue_growth_estimate NUMERIC(12,8),
    analyst_count INTEGER,
    analysts_up INTEGER,
    analysts_down INTEGER,
    analysts_unchanged INTEGER,
    guidance_direction VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    provider VARCHAR(128) NOT NULL,
    source_timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, as_of_date, fiscal_period, fiscal_year, provider)
);

CREATE INDEX IF NOT EXISTS idx_fundamental_estimates_symbol_period
    ON fundamental_estimate_snapshots(symbol, fiscal_period, fiscal_year, as_of_date DESC);
