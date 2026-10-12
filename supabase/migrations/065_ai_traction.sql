-- 065: AI-tailwind scoring on Rule Breaker snapshots — the computed
-- traction score plus its evidence breakdown.
ALTER TABLE rule_breaker_snapshots
    ADD COLUMN IF NOT EXISTS ai_traction DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ai_detail JSONB;
