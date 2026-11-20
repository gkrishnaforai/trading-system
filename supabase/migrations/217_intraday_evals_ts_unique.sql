-- intraday_evals.ts unique — the */15 cron job and the page's lazy
-- eval (>14min stale) race into the same wall-second and both INSERT.
-- Keep the oldest row of each collision, then enforce one eval per ts
-- so _persist's ON CONFLICT DO NOTHING has a target.

DELETE FROM intraday_evals a
USING intraday_evals b
WHERE a.ts = b.ts AND a.id > b.id;

CREATE UNIQUE INDEX IF NOT EXISTS intraday_evals_ts_key
    ON intraday_evals (ts);
