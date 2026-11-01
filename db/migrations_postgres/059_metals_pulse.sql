-- 059_metals_pulse.sql — Metals Pulse daily dashboard.
--
-- Two-layer engine: shared macro metals regime (real yields, dollar,
-- liquidity, credit stress, growth, inflation) + per-metal
-- fundamental/fear scores → accumulate/watch/reduce verdicts. Same
-- fear-entry philosophy as the equity selloff engine: discount is
-- the entry condition, intact structural demand is the thesis.
--
-- metals_snapshots: daily journaled state — macro label + full
-- payload (per-metal scores, verdicts, drivers, missing legs) so the
-- regime page reads one row and historical replays are possible.

SELECT pg_advisory_xact_lock(715059);

CREATE TABLE IF NOT EXISTS metals_snapshots (
    id            bigserial PRIMARY KEY,
    as_of         date NOT NULL UNIQUE,
    macro_regime  text,          -- precious_bullish|industrial_bullish|
                                 -- stagflationary|deflationary_risk|neutral
    payload       jsonb,         -- macro components + per-metal scores,
                                 -- verdicts, theses, missing legs
    created_at    timestamptz DEFAULT now()
);

-- nightly — FRED series lag a day; futures marks settle post-close.
INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES ('metals-pulse', 'Metals Pulse — metals regime + opportunity',
        'Gold/silver/copper macro regime + fundamental/fear scores →'
        ' accumulate/watch/wait verdicts, journaled',
        '30 22 * * 1-6', true, '{momentum}', 96, 60, 55)
ON CONFLICT (name) DO NOTHING;
