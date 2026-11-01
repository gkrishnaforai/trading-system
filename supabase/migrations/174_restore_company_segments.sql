-- 174_restore_company_segments.sql
-- company_segments was dropped by 136's dead-table sweep and missed
-- by 161's restore — observations.py reads it only behind the
-- ai_infra sector's segment_extraction flag, so the live-reference
-- audit skipped it. Prod logs 'relation does not exist' on every
-- ai_infra research run. Recreate the 125 schema verbatim.
SELECT pg_advisory_xact_lock(715174);

CREATE TABLE IF NOT EXISTS company_segments (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    segment         text NOT NULL,
    period          text NOT NULL,          -- e.g. FY2025, FY2026Q2
    revenue         numeric,
    gross_profit    numeric,
    growth_yoy      numeric,
    source          text,                   -- provider | filing | manual
    as_of           date NOT NULL,
    created_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, segment, period)
);
