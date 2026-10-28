-- 047_trade_plan_outcomes.sql — the closed-loop grader table.
-- trade_plans journals the plan + entry snapshot; trade_plan_events
-- journals the life transitions; this table joins them at close into
-- one accountable outcome row: realized R vs entry risk, which levels
-- were touched, which rules fired during the life, and the
-- rules_version that produced the entry context — so entry contexts
-- and spec versions grade against realized outcomes, not opinions.
CREATE TABLE IF NOT EXISTS trade_plan_outcomes (
    plan_id          bigint PRIMARY KEY REFERENCES trade_plans(id),
    symbol           text NOT NULL,
    use_case         text NOT NULL,
    direction        text NOT NULL DEFAULT 'long',
    -- entry context — the plan as it stood when opened
    entry_px         numeric,
    entry_date       date,
    stop_px          numeric,
    stop_basis       text,
    target1_px       numeric,
    target2_px       numeric,
    trail_rule       text,
    time_stop_days   int,
    qty              numeric,
    entry_mom        text,           -- momentum_state at entry
    entry_dip        text,           -- dip_phase at entry
    entry_pulse_action text,         -- pulse verdict at entry
    rules_version    text,           -- spec that produced the entry context
    -- the human's decision — the outcome itself
    close_px         numeric,
    closed_at        timestamptz,
    close_reason     text,
    days_held        int,
    realized_pct     numeric,        -- (close/entry−1)·sgn·100
    realized_r       numeric,        -- realized vs |entry−stop| risk
    -- the life story — transitions journaled while open
    hit_t1           boolean,
    hit_t2           boolean,
    stop_hit         boolean,
    invalidated      boolean,        -- thesis_invalidated fired
    events           jsonb,          -- ordered kind list (audit)
    graded_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tpo_use_case
    ON trade_plan_outcomes (use_case);
CREATE INDEX IF NOT EXISTS idx_tpo_rules_version
    ON trade_plan_outcomes (rules_version);
CREATE INDEX IF NOT EXISTS idx_tpo_entry_pulse
    ON trade_plan_outcomes (entry_pulse_action);
