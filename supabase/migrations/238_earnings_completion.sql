-- 238_earnings_completion.sql — the quarter-completion reconciler.
--
-- earnings_watch captures the print fast; the SLOW artifacts (10-Q
-- XBRL facts, the quarterly fundamentals row, the report) can lag
-- days-to-~45d. This ledger tracks per (symbol, earnings_date) what
-- is journaled vs still owed, and the nightly job fills what it can
-- and journals the rest honestly — never invents a check it didn't
-- verify. On any fill it re-runs the fundamentals chain so a late
-- 10-Q refreshes the evals that consumed the stale inputs.

CREATE TABLE IF NOT EXISTS earnings_completion (
    symbol        TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    checks        JSONB NOT NULL DEFAULT '{}'::jsonb,
                  -- {print|verdict|release8k|filing|xbrl|quarterly|
                  --  report|drivers: done|pending|n/a}
    missing       JSONB NOT NULL DEFAULT '[]'::jsonb,  -- pending checks
    filled        JSONB NOT NULL DEFAULT '[]'::jsonb,  -- fills the job made
    reanalyzed    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- evals re-run on fills
    status        TEXT NOT NULL DEFAULT 'tracking',
                  -- tracking | complete | expired
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_checked  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, earnings_date)
);
CREATE INDEX IF NOT EXISTS idx_earncomp_status
    ON earnings_completion (status, last_checked DESC);

-- nightly ~23:00 ET (04:00 UTC rides the DST boundary) — after the
-- watcher's evening sweep and the nightly chain; reconciles the
-- day's prints and the trailing 45d of owed artifacts.
INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, depends_on)
VALUES ('earnings-completion',
        'Earnings completion reconciler',
        'Per (symbol, print): track print/verdict/8-K/10-Q/XBRL/'
        'quarterly/report completeness, fill what is owed, '
        're-analyze on new data, alert on 10-Q/10-K landing',
        'job', '0 4 * * *', true,
        '{earnings-watch,flywheel,earnings-quality}')
ON CONFLICT (name) DO NOTHING;
