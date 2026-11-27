-- 230_liquidity_forward_stability.sql — the two new journals.
--
-- liquidity_forward_snapshots: the 4/8/12-week projected liquidity
--   outlook — two measures, scheduled mechanics, credit scenarios,
--   per-leg confidence, conditioned analogs. Daily (rides the
--   liquidity job; runs after the live snapshot, shares its fetch
--   budget). PIT: a replay sees what was actually published.
--
-- market_stability_snapshots: are buyers actually returning TODAY —
--   raw observations at fixed session marks (30m/60m/midday/close):
--   VWAP minutes + failed reclaims, VIX, breadth, AI leadership,
--   credit tone, session persistence, day structure. Raw over
--   composite: the label is derived FROM the raws; the raws are
--   what a false-signal audit needs. Both engines shadow —
--   decision_weight 0 until calibrated.

SELECT pg_advisory_xact_lock(715230);

CREATE TABLE IF NOT EXISTS liquidity_forward_snapshots (
    id            bigserial PRIMARY KEY,
    as_of         date NOT NULL UNIQUE,
    posture_hint  text,          -- supportive|neutral|caution|defensive
    payload       jsonb,         -- horizons, scheduled, scenarios,
                                 -- measures, analogs, confidence
    created_at    timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_stability_snapshots (
    id            bigserial PRIMARY KEY,
    session_date  date NOT NULL,
    mark          text NOT NULL, -- open|30m|60m|midday|close
    ts            timestamptz NOT NULL DEFAULT now(),
    readings      jsonb,         -- raw observations + derived label
    created_at    timestamptz DEFAULT now(),
    UNIQUE (session_date, mark)
);
CREATE INDEX IF NOT EXISTS market_stability_ts
    ON market_stability_snapshots (ts DESC);

-- every 15 min through the session — matches intraday-tape cadence;
-- each run journals at its mark, later runs update the same mark.
INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES ('market-stability',
        'Market stability — buyers returning?',
        'QQQ/SMH VWAP persistence + VIX + breadth + AI leadership +' ||
        ' credit tone + session persistence, journaled at fixed' ||
        ' session marks',
        '*/15 13-20 * * 1-5', true, '{live-bars}', 2, 10, 40)
ON CONFLICT (name) DO NOTHING;
