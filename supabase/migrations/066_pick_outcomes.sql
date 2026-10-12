-- 066: pick_outcomes — forward returns/MFE/MAE per daily_picks row,
-- plus which level (stop/target) was hit first. The edge board's
-- report card— feed alert_kind_stats-style learning later.
CREATE TABLE IF NOT EXISTS pick_outcomes (
    pick_date DATE NOT NULL,
    lane TEXT NOT NULL,
    symbol TEXT NOT NULL,
    horizon_days INT NOT NULL,
    entry_price DOUBLE PRECISION,
    ret_pct DOUBLE PRECISION,
    ret_vs_spy DOUBLE PRECISION,
    mfe_pct DOUBLE PRECISION,
    mae_pct DOUBLE PRECISION,
    hit TEXT,                          -- 'stop' | 'target' | NULL
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pick_date, lane, symbol, horizon_days)
);
