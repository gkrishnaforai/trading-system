-- 176_theme_intelligence.sql — Theme Intelligence engine.
--
-- Ranks registry themes by expected 6-12m opportunity (6-factor
-- score + 12m scenario-weighted fit) and maintains capped-weight
-- theme indices. Distinct from theme_rotation (member tape read)
-- and the index's job — the score prices expected opportunity,
-- the index membership prices what the index actually held.
--
-- theme_intelligence_snapshots: weekly dashboard payload.
-- theme_index_membership:     append-only PIT membership — index
--   history is what the index held on the date, never today's
--   survivor list projected backward.

SELECT pg_advisory_xact_lock(715176);

CREATE TABLE IF NOT EXISTS theme_intelligence_snapshots (
    id            bigserial PRIMARY KEY,
    as_of         date NOT NULL UNIQUE,
    payload       jsonb,         -- scenario probs + per-theme scores,
                                 -- legs, verdicts, index weights
    created_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS theme_index_membership (
    id            bigserial PRIMARY KEY,
    theme_key     text NOT NULL,
    as_of         date NOT NULL,
    version       text NOT NULL, -- pure | quality
    symbol        text NOT NULL,
    weight        double precision,
    score         double precision,
    created_at    timestamptz DEFAULT now(),
    UNIQUE (theme_key, as_of, version, symbol)
);
CREATE INDEX IF NOT EXISTS theme_index_membership_lookup
    ON theme_index_membership (theme_key, as_of);

-- weekly — Sundays, after the research sweep and Saturday liquidity
-- print so member legs are fresh.
INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES ('themes-pulse', 'Theme Intelligence — opportunity + indices',
        'Scenario-weighted theme opportunity + capped index weights,'
        ' journaled weekly',
        '0 13 * * 0', true, '{research}', 120, 60, 50)
ON CONFLICT (name) DO NOTHING;
