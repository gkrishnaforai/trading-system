-- 064: Rule Breaker traction layer — snapshot extra financials
-- (FCF margin, product-segment mix) and per-run milestone results so
-- typed milestones in checklist.milestones become machine-checked.
ALTER TABLE rule_breaker_snapshots
    ADD COLUMN IF NOT EXISTS fcf_margin DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS segments JSONB,      -- {segment: {rev, yoy, share}}
    ADD COLUMN IF NOT EXISTS milestones JSONB;    -- {label: true/false/null}
