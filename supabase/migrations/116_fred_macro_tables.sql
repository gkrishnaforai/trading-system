-- FRED macro-layer tables — raw series points + daily module snapshots.
-- Matches db_storage/models.py MacroSeriesPoint / MacroSnapshot exactly
-- (the ORM models shipped before the DDL did).

CREATE TABLE IF NOT EXISTS macro_series_points (
    series_id        text        NOT NULL,
    observation_date date        NOT NULL,
    value            numeric,
    source           text        DEFAULT 'fred',
    retrieved_at     timestamptz DEFAULT now(),
    PRIMARY KEY (series_id, observation_date)
);

CREATE INDEX IF NOT EXISTS idx_macro_series_points_series_date
    ON macro_series_points (series_id, observation_date);

CREATE TABLE IF NOT EXISTS macro_snapshots (
    id              bigserial    PRIMARY KEY,
    as_of_date      date         NOT NULL UNIQUE,
    module_scores   jsonb        DEFAULT '{}',
    overall_score   numeric,
    regime_probs    jsonb        DEFAULT '{}',
    portfolio_alloc jsonb        DEFAULT '{}',
    signals         jsonb        DEFAULT '{}',
    inputs_used     jsonb        DEFAULT '{}',
    is_month_end    boolean      DEFAULT false,
    created_at      timestamptz  DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_macro_snapshots_as_of_date
    ON macro_snapshots (as_of_date);
CREATE INDEX IF NOT EXISTS idx_macro_snapshots_is_month_end
    ON macro_snapshots (is_month_end, as_of_date);

-- scheduled job — before morning-regime so fresh module scores land
-- in the card— monthly FRED releases post ~8:30am ET (12:30 UTC)
insert into job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
values ('fred-macro', 'FRED structural layer',
        'Incremental FRED series (growth/labor/inflation/rates/credit/liquidity/housing/manufacturing) -> module scores -> macro_snapshots',
        'job', '10 13 * * 1-5', true, null, 14)
on conflict (name) do update set cron=excluded.cron, purpose=excluded.purpose,
       priority=excluded.priority;
