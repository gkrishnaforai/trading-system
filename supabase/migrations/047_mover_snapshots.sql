-- Daily memory for the market-movers screen.
-- One row per symbol per day the symbol appeared on FMP's movers lists and
-- survived the quality screen. Powers the accumulation streak
-- (days_on_list), volume trend, verdict persistence, and later outcome
-- measurement. Upsert on (symbol, as_of_date) so intraday refreshes keep
-- the latest values without duplicating rows.

CREATE TABLE IF NOT EXISTS mover_snapshots (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol        varchar(32) NOT NULL,
    as_of_date    date        NOT NULL,
    kinds         text[]      NOT NULL DEFAULT '{}',
    change_pct    numeric,
    volume        bigint,
    verdict       varchar(32),
    passed        integer,
    risk_level    varchar(16),
    risks         text[]      DEFAULT '{}',
    in_portfolio  boolean     NOT NULL DEFAULT false,
    in_watchlist  boolean     NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_mover_snapshots_date
    ON mover_snapshots (as_of_date DESC);
