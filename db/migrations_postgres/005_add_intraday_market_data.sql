CREATE TABLE IF NOT EXISTS raw_market_data_intraday (
  stock_symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  interval TEXT NOT NULL,
  open DOUBLE PRECISION,
  high DOUBLE PRECISION,
  low DOUBLE PRECISION,
  close DOUBLE PRECISION,
  volume BIGINT,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, ts, interval)
);

CREATE INDEX IF NOT EXISTS idx_raw_market_data_intraday_symbol_ts
  ON raw_market_data_intraday(stock_symbol, ts DESC);

CREATE INDEX IF NOT EXISTS idx_raw_market_data_intraday_symbol_interval_ts
  ON raw_market_data_intraday(stock_symbol, interval, ts DESC);
