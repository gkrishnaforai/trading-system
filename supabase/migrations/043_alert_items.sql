-- Alert inbox for catalyst-driven swing review triggers
-- Dedup via fingerprint— scan is replayable over a lookback window
CREATE TABLE IF NOT EXISTS alert_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol varchar(32) NOT NULL,
    event_type varchar(64) NOT NULL,
    direction varchar(16) NOT NULL,
    materiality varchar(16) NOT NULL,
    title text NOT NULL,
    detail jsonb,
    fingerprint varchar(255) NOT NULL UNIQUE,
    source varchar(64),
    source_timestamp timestamptz,
    in_portfolio boolean NOT NULL DEFAULT false,
    in_watchlist boolean NOT NULL DEFAULT false,
    status varchar(32) NOT NULL DEFAULT 'new',
    priority_score numeric,
    swing_run_id varchar(64),
    swing_action varchar(16),
    swing_summary text,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_alert_items_status_created
    ON alert_items (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_items_symbol_created
    ON alert_items (symbol, created_at DESC);
