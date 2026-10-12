-- 106_daily_sheet.sql — nightly "best expression per name" journal.
-- Conviction picks the names— this sheet picks the instrument
-- (stock zone / call LEAP / put LEAP / put watch), the armed entry
-- zone from swing structure, and the priced contract — graded on
-- zone_hit + ret_5d/20d vs SPY like the other journals.

CREATE TABLE IF NOT EXISTS daily_sheet_snapshots (
    id              bigserial PRIMARY KEY,
    snap_date       date NOT NULL,
    symbol          text NOT NULL,
    section         text NOT NULL,          -- stock_zone|call_leap|put_leap|put_watch
    lane            text,                   -- deploy|watch|hedge
    verdict         text,                   -- LEAPS direction verdict
    cycle_stage     text,
    conv_score      numeric,
    future_score    numeric,
    hedge_score     numeric,
    spot            numeric,
    zone_lo         numeric,
    zone_hi         numeric,
    trigger_px      numeric,
    stop_px         numeric,
    dip_phase       text,
    contract        jsonb,                  -- primary contract pick
    alt             jsonb,                  -- alternate (flip pick)
    iv_rank         numeric,
    iv_elevated     boolean,
    fv_upside_pct   numeric,
    reasons         jsonb,
    engine_version  text NOT NULL DEFAULT 'sheet_v1',
    zone_hit        boolean,
    ret_5d          numeric,
    ret_20d         numeric,
    vs_spy_20d      numeric,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snap_date, symbol, section)
);

CREATE INDEX IF NOT EXISTS daily_sheet_snapshots_date_idx
    ON daily_sheet_snapshots (snap_date);
CREATE INDEX IF NOT EXISTS daily_sheet_snapshots_sym_idx
    ON daily_sheet_snapshots (symbol, snap_date);
