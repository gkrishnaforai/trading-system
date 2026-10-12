-- Screener run history — one row per scan, results stored as a JSONB blob.
-- Enables "previous scanner results" on the page and survives worker
-- restarts (in-memory _screen_state is lost otherwise).

CREATE TABLE IF NOT EXISTS screen_runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ran_at        timestamptz NOT NULL DEFAULT now(),
    result_count  integer,
    errors        jsonb DEFAULT '[]',
    results       jsonb NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_screen_runs_ran_at
    ON screen_runs (ran_at DESC);
