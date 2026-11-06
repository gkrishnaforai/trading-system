-- SSEW fragility_daily — Systematic Selling Early Warning journal.
-- One row per day: composite vulnerability + per-leg scores/signals +
-- heuristic trigger probabilities + per-leg data-quality. Journaled
-- daily so realized outcomes can calibrate the heuristic priors later
-- (same journal-then-weigh pattern as correction_evals/forward_probs).
CREATE TABLE IF NOT EXISTS fragility_daily (
    as_of          DATE PRIMARY KEY,
    vulnerability  DOUBLE PRECISION,
    band           TEXT,
    probabilities  JSONB NOT NULL DEFAULT '{}',
    legs           JSONB NOT NULL DEFAULT '{}',
    signals        JSONB NOT NULL DEFAULT '{}',
    firing         JSONB NOT NULL DEFAULT '[]',
    validators     JSONB NOT NULL DEFAULT '{}',
    confidence     TEXT,
    coverage_pct   DOUBLE PRECISION,
    missing        JSONB NOT NULL DEFAULT '[]',
    read           TEXT,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- safety-net: the 065/066 tables lived only in db/migrations_postgres,
-- which supabase/migrations shadows — fresh deploys skipped them.
-- IF NOT EXISTS so prod (where they were created manually) is a no-op.
CREATE TABLE IF NOT EXISTS universe_snapshot (
    symbol         TEXT PRIMARY KEY,
    spot           DOUBLE PRECISION,
    spot_date      DATE,
    eps_ttm        DOUBLE PRECISION,
    fwd_eps        DOUBLE PRECISION,
    fy0_eps        DOUBLE PRECISION,
    fy2_eps        DOUBLE PRECISION,
    est_revision_pct DOUBLE PRECISION,
    num_analysts   INTEGER,
    rev_growth     DOUBLE PRECISION,
    fcf_ttm        DOUBLE PRECISION,
    market_cap     DOUBLE PRECISION,
    momentum_state TEXT,
    fv_expected    DOUBLE PRECISION,
    fv_upside_pct  DOUBLE PRECISION,
    lifecycle_stage INTEGER,
    category       TEXT,
    backlog_yoy    DOUBLE PRECISION,
    book_to_bill   DOUBLE PRECISION,
    snapshot_as_of TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS universe_snapshot_stale
    ON universe_snapshot (snapshot_as_of);

CREATE TABLE IF NOT EXISTS sector_timing_daily (
    as_of          DATE NOT NULL,
    sector_key     TEXT NOT NULL,
    etf            TEXT,
    opp_score      DOUBLE PRECISION,
    conf_score     DOUBLE PRECISION,
    trap_score     DOUBLE PRECISION,
    state          TEXT,
    signals        JSONB NOT NULL DEFAULT '{}',
    missing        JSONB NOT NULL DEFAULT '[]',
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, sector_key)
);

-- daily run after the close — needs the day's daily_bars landed.
-- sector-timing/universe-fill never got job rows (they only ran via
-- manual POST /refresh); fragility gets one from day one.
INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, timezone)
VALUES ('fragility', 'Systematic selling early warning',
        'Leverage/positioning fragility — vulnerability 0-100 + heuristic '
        'trigger probabilities, journaled daily for calibration',
        'job', '30 17 * * 1-5', true, 'America/New_York')
ON CONFLICT (name) DO UPDATE SET
  label = EXCLUDED.label, purpose = EXCLUDED.purpose,
  cron = EXCLUDED.cron, enabled = true,
  timezone = EXCLUDED.timezone, updated_at = now();
