CREATE TABLE IF NOT EXISTS portfolio_account_states (
    account_state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    account_equity NUMERIC(20,6),
    settled_cash NUMERIC(20,6),
    unsettled_cash NUMERIC(20,6),
    buying_power NUMERIC(20,6),
    portfolio_heat NUMERIC(12,8),
    source VARCHAR(128) NOT NULL DEFAULT 'manual_ui',
    reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'UNRECONCILED',
    missing_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_portfolio_account_states_latest
    ON portfolio_account_states(portfolio_id, as_of DESC);
