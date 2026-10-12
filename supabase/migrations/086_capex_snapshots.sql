-- AI capex-cycle snapshots: one row per calendar day so the meta loop
-- can correlate score/components with realized basket returns later.
CREATE TABLE IF NOT EXISTS capex_snapshots (
    as_of       date PRIMARY KEY,
    score       numeric NOT NULL,
    components  jsonb   NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS capex_snapshots_as_of_idx
    ON capex_snapshots (as_of DESC);
