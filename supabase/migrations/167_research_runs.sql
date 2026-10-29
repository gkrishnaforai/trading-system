-- 167_research_runs.sql — research engine journal.
-- One PIT row per symbol per day: the two versioned scores, the
-- recommendation, the full evidence pack (quarters, products,
-- commitments, challenge findings, coverage). Never overwritten
-- historically — the (symbol, as_of) key replays same-day runs.
SELECT pg_advisory_xact_lock(715167);

CREATE TABLE IF NOT EXISTS research_runs (
    id                   bigserial PRIMARY KEY,
    symbol               text NOT NULL,
    as_of                date NOT NULL,
    sector               text NOT NULL DEFAULT 'healthcare',
    business_model       text,
    ai_tailwind_score    numeric,
    business_strength    numeric,
    recommendation       text,
    scores               jsonb NOT NULL DEFAULT '{}',
    report               jsonb NOT NULL DEFAULT '{}',
    rules_version        text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS research_runs_sym_idx
    ON research_runs (symbol, as_of DESC);
