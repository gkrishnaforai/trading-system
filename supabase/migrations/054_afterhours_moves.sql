-- After-hours movers — one row per symbol per day capturing the post-market
-- read. Powers the "who's moving AH" board, AH alerts on held/watch names,
-- and tomorrow-planning signals (AH gap vs setup).

CREATE TABLE IF NOT EXISTS afterhours_moves (
    symbol        text NOT NULL,
    as_of_date    date NOT NULL,
    reg_close     numeric,
    ah_price      numeric,
    ah_pct        numeric,
    ah_time       timestamptz,
    in_portfolio  boolean DEFAULT false,
    in_watchlist  boolean DEFAULT false,
    source        text DEFAULT 'yahoo',
    created_at    timestamptz DEFAULT now(),
    updated_at    timestamptz DEFAULT now(),
    PRIMARY KEY (symbol, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_afterhours_moves_date
    ON afterhours_moves (as_of_date DESC);
