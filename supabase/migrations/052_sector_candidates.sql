-- Sector candidate rankings — latest ranked result stored as a JSONB blob.
-- Survives worker restarts (in-memory _cand_state is lost otherwise; the
-- job takes ~25 min cold so losing it on restart is expensive).

CREATE TABLE IF NOT EXISTS sector_candidate_runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ran_at        timestamptz NOT NULL DEFAULT now(),
    scored        integer,
    results       jsonb NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sector_candidate_runs_ran_at
    ON sector_candidate_runs (ran_at DESC);
