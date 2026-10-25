-- 039: version attribution for the learning lab (mirror of supabase 155)
--
-- spec_versions(engine, version) — one row per spec iteration, full
-- YAML snapshot. Every journaled rules_version joins here to recover
-- the exact spec that produced the eval; without it a version string
-- is a name whose meaning lives only in git history.
-- rules_version on daily_calls / board_decisions — the top-3 calls
-- and board lanes were journaled WITHOUT the spec version that
-- produced them; version-vs-version outcome grading needs the key.
SELECT pg_advisory_xact_lock(715155);

CREATE TABLE IF NOT EXISTS spec_versions (
    engine      TEXT        NOT NULL,   -- pulse | best_picks | lev_swings
    version     TEXT        NOT NULL,   -- rules.v1.4+a1b2c3d4 (content hash)
    spec        JSONB       NOT NULL,   -- full YAML snapshot at first use
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (engine, version)
);

ALTER TABLE daily_calls
    ADD COLUMN IF NOT EXISTS rules_version TEXT;
ALTER TABLE board_decisions
    ADD COLUMN IF NOT EXISTS rules_version TEXT;

-- seed the registry from lev's per-engine table so its history joins
INSERT INTO spec_versions (engine, version, spec, created_at)
SELECT 'lev_swings', version, spec, created_at FROM lev_spec_versions
ON CONFLICT (engine, version) DO NOTHING;
