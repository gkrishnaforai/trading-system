-- intraday_evals.ts unique — the */15 cron job and the page's lazy
-- eval (>14min stale) race into the same wall-second and both INSERT.
-- Keep the oldest row of each collision, then enforce one eval per ts
-- so _persist's ON CONFLICT DO NOTHING has a target.
-- The table itself is created by db/migrations_postgres/023 on the
-- app-migrations track; this track may run on DBs where it does not
-- exist yet, so create it idempotently first (schema mirrors 023).

CREATE TABLE IF NOT EXISTS intraday_evals (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    state       TEXT NOT NULL,
    readings    JSONB,
    outcome     TEXT,
    day_ret     NUMERIC(8,4),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

DELETE FROM intraday_evals a
USING intraday_evals b
WHERE a.ts = b.ts AND a.id > b.id;

CREATE UNIQUE INDEX IF NOT EXISTS intraday_evals_ts_key
    ON intraday_evals (ts);
