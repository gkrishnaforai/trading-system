-- Earnings reports — versioned, deterministic post-print report per
-- (symbol, earnings_date). The earnings watcher composes the report
-- from journaled evidence (earnings_data print, driver_commitments
-- guidance, fundamental_quarterly history, symbol_flywheel
-- expectations, earnings_watch verdict). Every regeneration appends
-- a new version — never overwrites — so the report history is the
-- audit trail of what we knew and when. Report content is advisory;
-- numbers trace to journaled rows, never invented.
CREATE TABLE IF NOT EXISTS earnings_reports (
    id            BIGSERIAL PRIMARY KEY,
    symbol        TEXT NOT NULL,
    earnings_date DATE NOT NULL,
    version       INTEGER NOT NULL,
    title         TEXT,
    report        JSONB NOT NULL,
    generated_by  TEXT NOT NULL DEFAULT 'earnings_watch',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, earnings_date, version)
);

CREATE INDEX IF NOT EXISTS earnings_reports_symbol_idx
    ON earnings_reports (symbol, earnings_date DESC, version DESC);

CREATE INDEX IF NOT EXISTS earnings_reports_date_idx
    ON earnings_reports (earnings_date DESC);
