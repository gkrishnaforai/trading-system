-- 063: daily_picks — the morning confluence board, persisted per day so
-- pick outcomes are measurable (the training loop for the scorer).
CREATE TABLE IF NOT EXISTS daily_picks (
    id BIGSERIAL PRIMARY KEY,
    pick_date DATE NOT NULL,
    lane TEXT NOT NULL,                -- 'swing' | 'breakout'
    rank INT NOT NULL,
    symbol TEXT NOT NULL,
    conviction DOUBLE PRECISION,
    components JSONB NOT NULL DEFAULT '{}',  -- score breakdown + evidence
    entry DOUBLE PRECISION,
    stop DOUBLE PRECISION,
    target DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (pick_date, lane, symbol)
);

CREATE INDEX IF NOT EXISTS idx_daily_picks_date ON daily_picks (pick_date DESC);
