-- Schedules for DB-driven cron orchestration (Go API is the single orchestrator)

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL CHECK (kind IN ('data_load', 'analysis_run', 'rebalance_run')),
    portfolio_id UUID NOT NULL,
    profile TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    next_run_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    last_run_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schedules_enabled_next_run_at
    ON schedules (enabled, next_run_at);

CREATE INDEX IF NOT EXISTS idx_schedules_portfolio
    ON schedules (portfolio_id);

CREATE INDEX IF NOT EXISTS idx_schedules_kind
    ON schedules (kind);

CREATE OR REPLACE FUNCTION set_updated_at_schedules()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_updated_at_schedules ON schedules;
CREATE TRIGGER trg_set_updated_at_schedules
BEFORE UPDATE ON schedules
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_schedules();
