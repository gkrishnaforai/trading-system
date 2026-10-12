-- market_defensive_snapshots — daily defensive-state assessments, the
-- bearish twin of market_transition_snapshots. The regime graph writes
-- one row per day (intraday reruns upsert)— hysteresis streaks are
-- counted over consecutive as_of_date scores by defensive_store.

CREATE TABLE IF NOT EXISTS market_defensive_snapshots (
    id             bigserial    PRIMARY KEY,
    as_of_date     date         NOT NULL UNIQUE,
    as_of          timestamptz,
    score          numeric,      -- 0-100, higher = more bearish evidence
    delta_1d       numeric,
    delta_5d       numeric,
    delta_20d      numeric,
    stage          text,         -- NORMAL|WATCH|HEDGE|DEFENSIVE|
                                 --  CAPITULATION|RECOVERY
    emergency      boolean      DEFAULT false,
    streak         integer,      -- consecutive days at/above the
                                 --  threshold that produced this stage
    components     jsonb        DEFAULT '{}',
    reasons        jsonb        DEFAULT '[]',
    data_sufficient boolean     DEFAULT false,
    rules_version  text,
    source         text         DEFAULT 'deterministic',
    created_at     timestamptz  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_defensive_snap_asof
    ON market_defensive_snapshots (as_of DESC);

-- recovery_deployments — journal of staged recovery-capital entries.
-- Capital itself is derived from realized hedge P&L— this table only
-- records what the human deployed, per stage.
CREATE TABLE IF NOT EXISTS recovery_deployments (
    id          bigserial    PRIMARY KEY,
    as_of       date         NOT NULL DEFAULT CURRENT_DATE,
    stage       integer      NOT NULL,    -- 1=20EMA reclaim
                                          --  2=50SMA, 3=200DMA
    symbol      text         NOT NULL,
    alloc_usd   numeric      NOT NULL,
    note        text,
    created_at  timestamptz  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recovery_deploy_asof
    ON recovery_deployments (as_of DESC);
