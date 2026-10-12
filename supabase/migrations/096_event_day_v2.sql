-- Event-day calls v2 — probabilities, model-deduced regime, print
-- data, Nasdaq sub-call, and post-event debrief.
-- probs: {p_green, p_red, p_choppy} — graded with Brier score, not
-- just binary hit/miss. regime_read: the model's own inference of
-- which constraint binds — compare vs the deterministic hint in
-- context.policy.binding_constraint vs the outcome.
ALTER TABLE event_day_calls
    ADD COLUMN IF NOT EXISTS probs jsonb,
    ADD COLUMN IF NOT EXISTS regime_read text,
    ADD COLUMN IF NOT EXISTS qqq_lean text,
    ADD COLUMN IF NOT EXISTS qqq_note text,
    ADD COLUMN IF NOT EXISTS qqq_ret_1d double precision,
    ADD COLUMN IF NOT EXISTS qqq_correct boolean,
    ADD COLUMN IF NOT EXISTS print_data jsonb,
    ADD COLUMN IF NOT EXISTS brier double precision,
    ADD COLUMN IF NOT EXISTS debrief text;
