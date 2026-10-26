-- data_ingestion_* — the refresh-manager tracking tables. The only
-- DDL ever written for them lived in hand-run python-worker/migrations
-- files with a pre-evolution schema (symbol/data_source/table_name);
-- the evolved columns the code actually writes (dataset, interval,
-- cursor_ts, retry_count, …) were never migrated anywhere, so prod
-- logs 'relation "data_ingestion_state" does not exist' every refresh.
-- This is the canonical union of every column the code references.

CREATE TABLE IF NOT EXISTS data_ingestion_state (
    id                   bigserial PRIMARY KEY,
    symbol               text NOT NULL,
    dataset              text NOT NULL,
    interval             text NOT NULL,
    source               text,
    historical_start_date date,
    historical_end_date   date,
    cursor_date          date,
    cursor_ts            timestamptz,
    last_attempt_at      timestamptz,
    last_success_at      timestamptz,
    last_ingested_at     timestamptz,
    records_count        int  NOT NULL DEFAULT 0,
    status               text NOT NULL DEFAULT 'pending',
    error_message        text,
    retry_count          int  NOT NULL DEFAULT 0,
    -- legacy columns kept nullable so older readers don't break
    data_source          text,
    table_name           text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);
-- unique (not PK) so ALTER-free — the code's ON CONFLICT target
CREATE UNIQUE INDEX IF NOT EXISTS data_ingestion_state_sdi_key
    ON data_ingestion_state (symbol, dataset, interval);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_state_status
    ON data_ingestion_state (status);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_state_symbol
    ON data_ingestion_state (symbol);

-- run ledger + per-run event stream (observability/audit.py)
CREATE TABLE IF NOT EXISTS data_ingestion_runs (
    run_id      uuid PRIMARY KEY,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL DEFAULT 'running',
    environment text,
    git_sha     text,
    metadata    jsonb DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_runs_started
    ON data_ingestion_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_runs_status
    ON data_ingestion_runs (status);

CREATE TABLE IF NOT EXISTS data_ingestion_events (
    id                 bigserial PRIMARY KEY,
    run_id             text NOT NULL,   -- uuid strings AND 'fallback_*' ids
    event_ts           timestamptz NOT NULL DEFAULT now(),
    level              text NOT NULL,
    provider           text,
    operation          text,
    symbol             text,
    duration_ms        int,
    records_in         int,
    records_saved      int,
    message            text,
    error_type         text,
    error_message      text,
    root_cause_type    text,
    root_cause_message text,
    context            jsonb DEFAULT '{}'::jsonb,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_run
    ON data_ingestion_events (run_id);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_ts
    ON data_ingestion_events (event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_data_ingestion_events_level
    ON data_ingestion_events (level);
