-- 111_lt_power.sql — long-duration earnings-power repricing lens.
-- Append-only journal for lt_power runs: the LT implied-value band
-- (eps_lt × exit multiple), the repricing checklist, and the resolved
-- inputs — same training-data pattern as fair_value_v2_runs.

CREATE TABLE IF NOT EXISTS lt_power_runs (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    symbol          text NOT NULL,
    as_of           date NOT NULL,
    spot            double precision,
    lt_period       date,
    eps_near        double precision,
    eps_lt_avg      double precision,
    eps_lt_low      double precision,
    eps_lt_high     double precision,
    lt_analysts     double precision,
    lt_band         jsonb,
    checklist       jsonb,
    repricing_setup text,
    implied_lt_pe   double precision,
    lt_gap_pct      double precision,
    inputs_hash     text,
    model_version   text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS lt_power_runs_symbol_asof
    ON lt_power_runs (symbol, as_of DESC);
