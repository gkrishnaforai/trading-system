CREATE TABLE IF NOT EXISTS data_ingestion_state (
  stock_symbol TEXT NOT NULL,
  dataset TEXT NOT NULL,
  interval TEXT NOT NULL,
  source TEXT,

  historical_start_date DATE,
  historical_end_date DATE,

  cursor_date DATE,
  cursor_ts TIMESTAMPTZ,

  last_attempt_at TIMESTAMPTZ,
  last_success_at TIMESTAMPTZ,

  status TEXT NOT NULL DEFAULT 'idle',
  error_message TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (stock_symbol, dataset, interval)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_state_dataset_status ON data_ingestion_state(dataset, status);
CREATE INDEX IF NOT EXISTS idx_ingestion_state_symbol_dataset ON data_ingestion_state(stock_symbol, dataset);


CREATE TABLE IF NOT EXISTS raw_market_data_daily (
  stock_symbol TEXT NOT NULL,
  trade_date DATE NOT NULL,
  open DOUBLE PRECISION,
  high DOUBLE PRECISION,
  low DOUBLE PRECISION,
  close DOUBLE PRECISION,
  adj_close DOUBLE PRECISION,
  volume BIGINT,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_raw_market_data_daily_symbol_date ON raw_market_data_daily(stock_symbol, trade_date DESC);


CREATE TABLE IF NOT EXISTS indicators_daily (
  stock_symbol TEXT NOT NULL,
  trade_date DATE NOT NULL,
  sma_50 DOUBLE PRECISION,
  sma_200 DOUBLE PRECISION,
  ema_20 DOUBLE PRECISION,
  rsi_14 DOUBLE PRECISION,
  macd DOUBLE PRECISION,
  macd_signal DOUBLE PRECISION,
  macd_hist DOUBLE PRECISION,
  signal TEXT,
  confidence_score DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_indicators_daily_symbol_date ON indicators_daily(stock_symbol, trade_date DESC);
