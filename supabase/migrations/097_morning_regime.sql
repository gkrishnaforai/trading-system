-- Morning regime snapshots — the daily engine, not the event-day one.
-- Every morning: deterministic 7-bucket score → 5-regime class →
-- LLM explains (evidence-linked JSON) → journaled → graded at 5d/20d.
-- Buckets score independently so "which factor was wrong" is a
-- learnable answer, not a lumped verdict.
CREATE TABLE IF NOT EXISTS morning_regime_snapshots (
    id           bigserial PRIMARY KEY,
    as_of        date NOT NULL UNIQUE,
    regime       text NOT NULL,     -- strong_risk_on|risk_on|neutral|
                                    --   risk_off|stress
    ai_regime    text,              -- risk_on|risk_off for the AI book
    score        int,               -- deterministic composite 0-100
    confidence   text,              -- low|moderate|high
    buckets      jsonb,             -- per-factor scores + inputs
    llm          jsonb,             -- explanation, evidence, contradictions
    verdict      jsonb,             -- {regime,confidence,ai_regime,drivers,
                                    --   contradictions,invalidations,qqq_lean}
    spy_ret_5d   double precision,  -- graded
    spy_ret_20d  double precision,
    qqq_ret_5d   double precision,
    qqq_ret_20d  double precision,
    regime_correct boolean,         -- did the call match the tape?
    brier        double precision,
    created_at   timestamptz DEFAULT now(),
    graded_at    timestamptz
);
CREATE INDEX IF NOT EXISTS morning_regime_date_idx
    ON morning_regime_snapshots (as_of DESC);
