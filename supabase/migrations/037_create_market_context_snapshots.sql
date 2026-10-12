-- Reusable deterministic market context for same-session agent runs.
CREATE TABLE IF NOT EXISTS market_context_snapshots (
    context_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_date DATE NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    horizon VARCHAR(32) NOT NULL DEFAULT 'swing',
    snapshot JSONB NOT NULL,
    facts JSONB NOT NULL,
    regime JSONB NOT NULL,
    transition JSONB NOT NULL DEFAULT '{}'::jsonb,
    strategy_environments JSONB NOT NULL DEFAULT '{}'::jsonb,
    event_context JSONB,
    event_reaction JSONB,
    provider_routes JSONB NOT NULL DEFAULT '{}'::jsonb,
    rules_version VARCHAR(128) NOT NULL DEFAULT 'market-context-v1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(session_date, horizon, rules_version)
);

CREATE INDEX IF NOT EXISTS idx_market_context_session_asof
    ON market_context_snapshots(session_date, horizon, as_of DESC);
