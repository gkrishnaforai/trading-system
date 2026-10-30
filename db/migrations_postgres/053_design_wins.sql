-- 053_design_wins.sql — journaled design-win lifecycle for the
-- AI-infra research module. The entity the spec asks for:
-- announcement ≠ win ≠ production revenue; each row carries the
-- stage ladder + revenue_confirmed so conversion is deterministic
-- and PIT-replayable.
SELECT pg_advisory_xact_lock(715053);

CREATE TABLE IF NOT EXISTS design_wins (
    id                bigserial PRIMARY KEY,
    symbol            text NOT NULL,
    customer          text NOT NULL,          -- 'Amazon', 'Google', 'unnamed hyperscaler'
    product           text NOT NULL,          -- 'AEC', 'optical DSP', 'retimer'
    stage             text NOT NULL DEFAULT 'announced',
                      -- announced | sampling | qualification |
                      -- production | scaling
    announced_at      date,
    revenue_confirmed boolean NOT NULL DEFAULT false,
    evidence          jsonb,                  -- {quote, source, period, confidence}
    source            text NOT NULL DEFAULT 'research_extract',
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, customer, product)
);

CREATE INDEX IF NOT EXISTS idx_design_wins_sym
    ON design_wins (symbol, stage);
