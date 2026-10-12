-- Canonical OHLCV store — ONE batch fetch per session, read by every
-- consumer (momentum flags, pattern priors, swing pilot, lookups).
-- Written by the momentum job's bars refresh; jobs that need bars read
-- here instead of hitting yfinance again.
CREATE TABLE IF NOT EXISTS daily_bars (
    symbol  text              NOT NULL,
    date    date              NOT NULL,
    open    double precision,
    high    double precision,
    low     double precision,
    close   double precision,
    volume  bigint,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX IF NOT EXISTS daily_bars_symbol_idx
    ON daily_bars (symbol, date DESC);
