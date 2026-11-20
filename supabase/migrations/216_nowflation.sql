-- 216_nowflation.sql — Nowflation open-data journal.
--
-- One row per publish date: the gauge/realtime readings, the gap to
-- official CPI, the pre-registered print forecast, and the raw payload
-- for anything we didn't decompose. Consumers:
--   fed_path      inflation leg fallback (macro_snapshots is empty —
--                 the module score never fires without a daily source)
--   morning       catalyst enrichment — 'expected' on upcoming CPI
--                 events so the call card can show the forecast
--   narrative     industry_research claims the grader validates when
--                 the real print lands (their scoreboard + our own)
--
-- Idempotent on as_of — a same-day republish updates the row (their
-- 'live' record type can revise intraday).

CREATE TABLE IF NOT EXISTS nowflation_daily (
    as_of                  DATE PRIMARY KEY,
    realtime_yoy_pct       NUMERIC,
    realtime_dod_pp        NUMERIC,
    realtime_wow_pp        NUMERIC,
    cpi_gauge_yoy_pct      NUMERIC,
    cpi_gauge_method       TEXT,
    official_cpi_yoy_pct   NUMERIC,
    official_cpi_month     TEXT,
    gauge_gap_pp           NUMERIC,          -- gauge − official
    truflation_yoy_pct     NUMERIC,
    print_forecast_month   TEXT,             -- e.g. '2026-11'
    print_forecast_yoy     NUMERIC,          -- displayed headline call
    model_forecast_yoy     NUMERIC,          -- in-house component model
    model_version          TEXT,
    record_type            TEXT,
    raw                    JSONB,
    fetched_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nowflation_daily_asof
    ON nowflation_daily (as_of DESC);

-- schedule — slots between fred-macro (13:10 UTC) and fed-path
-- (13:30 UTC): Nowflation publishes ~13:05, so the inflation leg
-- has today's gauge before the rate-path composition reads it.
UPDATE job_definitions
SET cron = '25 13 * * 1-5',
    enabled = true,
    depends_on = ARRAY['fred-macro']::text[],
    updated_at = now()
WHERE name = 'nowflation';
