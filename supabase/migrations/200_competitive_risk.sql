-- 200_competitive_risk.sql — Competitive Disruption & Substitution
-- Engine. Two tables:
--   competitive_threats  — append-only evidence journal (claims:
--                          competitor, segment, stage, share-at-risk
--                          ranges, direction). draft->approved->stale;
--                          nothing scores until approved.
--   competitive_scores   — quarterly CRS journal per symbol
--                          (append-only like cycle_snapshots).
SELECT pg_advisory_xact_lock(715200);

CREATE TABLE IF NOT EXISTS competitive_threats (
    id                bigserial PRIMARY KEY,
    symbol            text NOT NULL,
    competitor        text NOT NULL,     -- 'SiFive', 'RISC-V ecosystem',
                                         -- 'in-house ASIC', 'white-box'
    threat_type       text NOT NULL,     -- substitution | insourcing |
                                         -- platform | open_source |
                                         -- geo_localization | pricing
    segment           text NOT NULL,     -- revenue pool it hits:
                                         -- 'dc CPU IP', 'AEC', 'HBM'
    stage             text NOT NULL,     -- announced | prototype |
                                         -- design_win | qualification |
                                         -- production | scaled
    direction         text NOT NULL,     -- threat | opportunity | mixed
    share_at_risk_lo  numeric,           -- RANGE: fraction of the pool
    share_at_risk_hi  numeric,           --   plausibly lost (or won)
    probability       numeric,           -- 0-1
    displacement_lo   smallint,          -- expected displacement year
    displacement_hi   smallint,          --   range, never a point
    claim             text NOT NULL,     -- human-readable statement
    source            text NOT NULL,     -- filing | earnings_call |
                                         -- news | manual | llm_extract |
                                         -- framework_doc
    source_ref        text,
    source_date       timestamptz,
    confidence        text NOT NULL DEFAULT 'medium',
    status            text NOT NULL DEFAULT 'draft',   -- draft|approved|
                                         -- rejected|stale
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, competitor, segment, source_ref)
);

CREATE INDEX IF NOT EXISTS idx_ct_symbol
    ON competitive_threats (symbol, status);
CREATE INDEX IF NOT EXISTS idx_ct_stage
    ON competitive_threats (stage, status);

CREATE TABLE IF NOT EXISTS competitive_scores (
    id                   bigserial PRIMARY KEY,
    symbol               text NOT NULL,
    quarter_label        text NOT NULL,
    as_of                date NOT NULL,
    crs                  numeric,        -- 0-100 resilience composite
    coverage_pct         numeric,
    substitution_resist  numeric,        -- 20
    competitive_position numeric,        -- 20
    insourcing_resist    numeric,        -- 15
    technology_moat      numeric,        -- 15
    ecosystem_switching  numeric,        -- 15
    value_capture        numeric,        -- 15
    opportunity_credit   numeric,        -- 0-15 — threats that help
    revenue_at_risk_lo   numeric,        -- share-of-revenue index range
    revenue_at_risk_hi   numeric,
    displacement_confirmed boolean,      -- production+ threat, sized
    risk_trend           text,           -- improving|stable|deteriorating|new
    top_threats          jsonb NOT NULL DEFAULT '[]',
    components           jsonb NOT NULL DEFAULT '{}',
    flags                jsonb NOT NULL DEFAULT '[]',
    rules_version        text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, quarter_label, as_of)
);

CREATE INDEX IF NOT EXISTS idx_cs_sym_q
    ON competitive_scores (symbol, quarter_label, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_cs_displacement
    ON competitive_scores (displacement_confirmed, quarter_label);

-- Weekly cadence alongside ai-cycle — cheap: reads journaled rows only.
INSERT INTO job_definitions (name, label, cron, enabled, cooldown_min,
                             priority)
VALUES ('competitive-risk', 'Competitive disruption & substitution (weekly)',
        '45 6 * * 6', true, 720, 41)
ON CONFLICT (name) DO UPDATE SET
    cron         = COALESCE(job_definitions.cron, EXCLUDED.cron),
    enabled      = CASE WHEN job_definitions.cron IS NULL
                        THEN EXCLUDED.enabled
                        ELSE job_definitions.enabled END,
    priority     = EXCLUDED.priority;
