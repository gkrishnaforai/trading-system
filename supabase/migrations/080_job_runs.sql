-- job_runs — durable last-run ledger for the board refresh panel.
-- The in-memory _jobs dict dies with every worker restart; this table
-- makes 'how stale is this layer' survive deploys.
CREATE TABLE IF NOT EXISTS job_runs (
    id         serial PRIMARY KEY,
    name       text NOT NULL,
    ran_at     timestamptz NOT NULL DEFAULT now(),
    duration_s double precision,
    error      text,
    result     jsonb
);
CREATE INDEX IF NOT EXISTS job_runs_name_idx
    ON job_runs (name, ran_at DESC);
