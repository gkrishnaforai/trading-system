-- Daily deterministic bullish-transition history.
CREATE TABLE IF NOT EXISTS market_transition_snapshots (
    as_of_date DATE PRIMARY KEY,
    as_of TIMESTAMPTZ NOT NULL,
    score NUMERIC(8,3) NOT NULL,
    delta_1d NUMERIC(8,3),
    delta_5d NUMERIC(8,3),
    delta_20d NUMERIC(8,3),
    stage VARCHAR(32) NOT NULL,
    dip_buying_environment VARCHAR(32) NOT NULL,
    size_multiplier NUMERIC(8,4) NOT NULL,
    components JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    rules_version VARCHAR(128) NOT NULL,
    source VARCHAR(128) NOT NULL DEFAULT 'deterministic',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_transition_snapshots_asof
    ON market_transition_snapshots(as_of DESC);
