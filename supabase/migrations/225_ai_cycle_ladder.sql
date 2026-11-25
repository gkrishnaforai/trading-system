-- ai_cycle_ladder_daily: the AI-cycle theme ladder — per-stage
-- tape / forward-growth / evidence / funding legs plus market
-- regime, journaled daily so the rotation call is graded, not
-- asserted. Payload schema mirrors inference_ladder.compute().
CREATE TABLE IF NOT EXISTS ai_cycle_ladder_daily (
    as_of        DATE NOT NULL PRIMARY KEY,
    payload      JSONB NOT NULL DEFAULT '{}',
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
