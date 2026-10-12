ALTER TABLE readiness_evals
    ADD COLUMN IF NOT EXISTS rank numeric,
    ADD COLUMN IF NOT EXISTS parts jsonb;
CREATE INDEX IF NOT EXISTS readiness_evals_rank_idx
    ON readiness_evals (use_case, as_of, rank DESC);
