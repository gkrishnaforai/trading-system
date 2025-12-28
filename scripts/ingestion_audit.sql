CREATE TABLE IF NOT EXISTS data_ingestion_runs (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    environment VARCHAR(32),
    git_sha VARCHAR(64),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS data_ingestion_events (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES data_ingestion_runs(run_id) ON DELETE CASCADE,
    event_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level VARCHAR(16) NOT NULL,
    provider VARCHAR(64),
    operation VARCHAR(128) NOT NULL,
    symbol VARCHAR(32),
    duration_ms INTEGER,
    records_in INTEGER,
    records_saved INTEGER,
    message TEXT,
    error_type VARCHAR(256),
    error_message TEXT,
    root_cause_type VARCHAR(256),
    root_cause_message TEXT,
    context JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_run_ts ON data_ingestion_events(run_id, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_symbol_ts ON data_ingestion_events(symbol, event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_provider_ts ON data_ingestion_events(provider, event_ts DESC);
