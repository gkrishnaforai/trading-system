-- Fundamental Progress & Upside Engine — thesis layer.
-- thesis_watches gains hypothesis linkage + evidence staging so the
-- existing falsifiable-watch journal IS the progress tracker (no
-- parallel journal). symbol_thesis holds the per-stock roll-up:
-- archetype, per-hypothesis statuses, veto results, overall health.
ALTER TABLE thesis_watches
    ADD COLUMN IF NOT EXISTS hypothesis_id TEXT,
    ADD COLUMN IF NOT EXISTS stage TEXT,
    ADD COLUMN IF NOT EXISTS archetype TEXT,
    ADD COLUMN IF NOT EXISTS expected_direction TEXT,
    ADD COLUMN IF NOT EXISTS failure_condition TEXT,
    ADD COLUMN IF NOT EXISTS valuation_impact TEXT;

CREATE TABLE IF NOT EXISTS symbol_thesis (
    symbol TEXT PRIMARY KEY,
    archetype TEXT NOT NULL,
    secondary TEXT,
    hypotheses JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'unknown',
    score NUMERIC,
    vetoes JSONB,
    detail JSONB,
    as_of DATE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- nightly at 22:20 UTC — after fund-flags so it classifies on today's
-- metrics; cheap (deterministic, pilot universe only)
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('thesis-check', 'Archetype thesis tracker', '20 22 * * *', true)
ON CONFLICT (name) DO NOTHING;
