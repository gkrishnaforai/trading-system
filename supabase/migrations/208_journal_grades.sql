-- journal_kind_stats — the substrate→feedback scoreboard. For every
-- journal kind (recovery states, thesis transitions, crypto stance,
-- selloff classes, insider clusters): forward returns at 5/10/20d
-- per bucket, aggregated weekly. Descriptive, not prescriptive —
-- bounded weight writes stay in meta_learn.
CREATE TABLE IF NOT EXISTS journal_kind_stats (
    id         BIGSERIAL PRIMARY KEY,
    kind       TEXT NOT NULL,        -- recovery_state|thesis_transition|...
    bucket     TEXT NOT NULL,        -- EXHAUSTION|broken|accumulation|...
    horizon    INT  NOT NULL,        -- 5|10|20 trading days (approx)
    n          INT  NOT NULL,
    win_rate   NUMERIC,              -- % of rows with fwd ret > 0
    avg_ret    NUMERIC,
    median_ret NUMERIC,
    reliable   BOOLEAN NOT NULL DEFAULT false,  -- n >= 20
    graded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jks_kind_bucket
    ON journal_kind_stats (kind, bucket, horizon);

-- weekly Sunday 07:00 UTC — forward horizons need days to mature;
-- a weekly pass is the honest cadence for signal grading
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('journal-grades', 'Journal signal grading', '0 7 * * 0', true)
ON CONFLICT (name) DO NOTHING;
