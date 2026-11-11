-- 197_intraday_recovery_daily.sql — durable day-summary for the 5m
-- recovery engine. Raw evals age out at 10 days (5m bars at 35 for
-- RVOL baselines); this one-row-per-symbol-per-day rollup is the
-- permanent record for calibration/backtest grading.
SELECT pg_advisory_xact_lock(715197);

CREATE TABLE IF NOT EXISTS intraday_recovery_daily (
    symbol              TEXT NOT NULL,
    as_of               DATE NOT NULL,
    final_signal        TEXT,
    final_score         NUMERIC,
    recovery_score      NUMERIC,
    accumulation_score  NUMERIC,
    max_vwap_hold_min   INT,
    confirmed_minutes   INT,
    end_delta_vol       NUMERIC,
    end_rvol            NUMERIC,
    n_evals             INT,
    n_transitions       INT,
    signals             JSONB,
    first_eval          TIMESTAMPTZ,
    last_eval           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS idx_ird_asof
    ON intraday_recovery_daily (as_of DESC);
