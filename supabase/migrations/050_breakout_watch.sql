-- 050_breakout_watch.sql
-- Pre-breakout watchlist: symbols within ~5% of their 20d high, maintained
-- by each screener run; an intraday check fires an alert the hour price
-- crosses the pivot — instead of discovering the breakout at next EOD scan.

CREATE TABLE IF NOT EXISTS breakout_watch (
    symbol           text PRIMARY KEY,
    pivot            numeric NOT NULL,            -- 20d high = trigger level
    score            numeric,                     -- screener score when added
    setup_type       text,                        -- setup at time of watch
    added_at         timestamptz NOT NULL DEFAULT now(),
    last_price       numeric,
    last_checked_at  timestamptz,
    distance_pct     numeric,                     -- last_price/pivot - 1
    status           text NOT NULL DEFAULT 'watching',  -- watching | triggered | expired
    triggered_at     timestamptz,
    trigger_price    numeric,
    days_on_watch    int NOT NULL DEFAULT 1,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_breakout_watch_status ON breakout_watch(status);
