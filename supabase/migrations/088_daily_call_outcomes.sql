-- Grading for the daily top-3 calls — the training ledger for the
-- swing-call engine. One row per call, evolving until resolved:
-- call-day EOD close (entry quality), then stop-vs-target first
-- touch (plan quality), plus 5/10/20d returns for calibration.
CREATE TABLE IF NOT EXISTS daily_call_outcomes (
    id            bigserial PRIMARY KEY,
    call_id       bigint NOT NULL REFERENCES daily_calls(id),
    call_date     date NOT NULL,
    symbol        text NOT NULL,
    entry_px      double precision,
    stop_px       double precision,
    target_px     double precision,
    eod_close     double precision,        -- same-day close
    ret_eod       double precision,        -- entry -> EOD %
    ret_5d        double precision,
    ret_10d       double precision,
    ret_20d       double precision,
    mfe           double precision,        -- best excursion while open
    mae           double precision,        -- worst excursion while open
    resolution    text NOT NULL DEFAULT 'open',
                  -- target_first | stop_first | expired | open
    resolved_date date,
    days_held     int,
    graded_at     timestamptz DEFAULT now(),
    UNIQUE (call_id)
);
CREATE INDEX IF NOT EXISTS dco_date_idx ON daily_call_outcomes (call_date DESC);
CREATE INDEX IF NOT EXISTS dco_res_idx  ON daily_call_outcomes (resolution);
