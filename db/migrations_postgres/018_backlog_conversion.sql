-- Backlog-conversion + billings-health fields on symbol_sec_facts.
-- rpo_yoy: RPO vs the same period a year ago — backlog still building
-- while revenue decelerates = conversion delay, not demand loss.
-- crpo_share: share of RPO due within 12m (NOW files the % tag, not $).
-- def_rev_*: current deferred revenue — billings lead revenue.
-- gw_impair_fy: latest FY goodwill impairment — past-deal quality.
ALTER TABLE symbol_sec_facts
    ADD COLUMN IF NOT EXISTS rpo_yoy NUMERIC,
    ADD COLUMN IF NOT EXISTS crpo_share NUMERIC,
    ADD COLUMN IF NOT EXISTS def_rev_cur NUMERIC,
    ADD COLUMN IF NOT EXISTS def_rev_yoy NUMERIC,
    ADD COLUMN IF NOT EXISTS gw_impair_fy NUMERIC;
