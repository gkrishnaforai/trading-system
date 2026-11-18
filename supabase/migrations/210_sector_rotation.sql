-- sector_rotation_daily — leadership-deterioration journal. One row
-- per watched sector/day: risk state, renormalized leg scores,
-- destination leaderboard, flow status (unavailable|pending|
-- confirmed|absent — never proxied), breadth coverage so the
-- tracked-subset caveat travels with every row.
CREATE TABLE IF NOT EXISTS sector_rotation_daily (
    id               BIGSERIAL PRIMARY KEY,
    sector           TEXT NOT NULL,          -- SMH (pilot) ...
    as_of            DATE NOT NULL,
    state            TEXT NOT NULL,          -- healthy|early_deterioration|
                                           --   rotation_developing|
                                           --   rotation_probable
    risk_score       NUMERIC,                -- 0-100, renormalized over
                                           --   available legs
    dest_scores      JSONB,                  -- destination leaderboard
    legs             JSONB,                  -- per-leg score+inputs+missing
    flow_status      TEXT,                   -- unavailable|pending|...
    breadth_coverage INT,                    -- tracked names with data
    missing_inputs   JSONB,
    detail           JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sector, as_of)
);

CREATE INDEX IF NOT EXISTS idx_srd_sector_date
    ON sector_rotation_daily (sector, as_of DESC);

-- daily 06:55 UTC — after bars land, before the morning read
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('sector-rotation', 'Sector rotation early warning',
        '55 6 * * *', true)
ON CONFLICT (name) DO NOTHING;
