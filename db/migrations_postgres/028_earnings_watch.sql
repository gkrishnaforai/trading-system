-- earnings_watch — per-print capture log for the earnings-day
-- watcher. When a tracked name's report lands (actuals arrive via
-- yfinance or the 8-K drops on EDGAR), the watcher journals the
-- print, the thesis status before/after, and the verdict that
-- feeds the alert. One row per symbol per print — the unique key
-- makes the 30-min poll idempotent.

CREATE TABLE IF NOT EXISTS earnings_watch (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    earnings_date   DATE NOT NULL,
    session         TEXT,
    eps_est         NUMERIC,
    eps_actual      NUMERIC,
    surprise_pct    NUMERIC,
    rev_est         NUMERIC,
    thesis_before   TEXT,
    thesis_after    TEXT,
    verdict         TEXT NOT NULL,        -- improving|deteriorating|mixed|pending
    detail          JSONB,
    alerted         BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, earnings_date)
);

CREATE INDEX IF NOT EXISTS earnings_watch_date_idx
    ON earnings_watch (earnings_date DESC);
