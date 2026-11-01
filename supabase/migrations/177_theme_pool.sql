-- 177_theme_pool.sql — theme_registry.pool: the candidate pool.
--
-- members = index constituents (weighted, eligibility-gated).
-- pool    = broader watch-list per theme (small/mid-cap, speculative
--           pure-plays) — ranked by the same constituent score and
--           journaled in the snapshot payload, but never weighted
--           into the index until promoted into members. Broaden the
--           funnel, not the index.

SELECT pg_advisory_xact_lock(715177);

ALTER TABLE theme_registry
    ADD COLUMN IF NOT EXISTS pool jsonb NOT NULL DEFAULT '{}'::jsonb;
