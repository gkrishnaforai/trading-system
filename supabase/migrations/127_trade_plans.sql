-- 127_trade_plans.sql — the human-in-the-loop trade plan journal.
-- A plan binds a recorded entry (px/date/use_case) to the engine's
-- levels at that moment: structure stop, R-targets, trail rule, time
-- stop, and a snapshot of the inputs that produced the suggestion.
-- Status is computed live by the same YAML rule engine (plan_status
-- section) — transitions journal into trade_plan_events = the alert
-- feed. The system advises levels and flags transitions; the human
-- decides and closes the plan.

CREATE TABLE IF NOT EXISTS trade_plans (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    use_case        text NOT NULL,              -- swing|invest|leap_call|leap_put
    direction       text NOT NULL DEFAULT 'long', -- long|short (leap_put = short the underlying thesis)
    entry_px        numeric NOT NULL,
    entry_date      date NOT NULL DEFAULT CURRENT_DATE,
    qty             numeric,
    -- the plan — engine-suggested, human-editable at creation
    stop_px         numeric,
    stop_basis      text,                       -- swing_low|prior_low|atr2|pct|manual
    target1_px      numeric,                    -- default ~1.5R
    target2_px      numeric,                    -- default ~2R
    trail_rule      text,                       -- hl_ratchet|ema20|ema50|none
    time_stop_days  int,                        -- sessions w/o follow-through → stalled
    thesis          text,
    entry_snapshot  jsonb,                      -- readiness state + mom levels
    -- lifecycle
    status          text NOT NULL DEFAULT 'open', -- open|closed|cancelled
    last_status     text,                       -- last computed plan_status
    closed_at       timestamptz,
    close_px        numeric,
    close_reason    text,
    created_at      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tp_open
    ON trade_plans (symbol, status) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS trade_plan_events (
    id              bigserial PRIMARY KEY,
    plan_id         bigint NOT NULL REFERENCES trade_plans(id),
    symbol          text NOT NULL,
    as_of           date NOT NULL DEFAULT CURRENT_DATE,
    kind            text NOT NULL,              -- plan_status value that fired
    action_hint     text,                       -- exit|scale|raise_stop|review|hold
    message         text,
    ctx             jsonb,                      -- the numbers that produced it
    seen            bool NOT NULL DEFAULT false,
    created_at      timestamptz DEFAULT now(),
    UNIQUE (plan_id, as_of, kind)               -- first write of the day wins
);
CREATE INDEX IF NOT EXISTS idx_tpe_unseen
    ON trade_plan_events (seen, as_of) WHERE NOT seen;
