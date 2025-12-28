DROP TABLE IF EXISTS indicators_daily;
DROP TABLE IF EXISTS raw_market_data_daily;

CREATE TABLE raw_market_data_daily (
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

CREATE INDEX idx_raw_market_data_daily_symbol_date ON raw_market_data_daily(stock_symbol, trade_date DESC);


CREATE TABLE indicators_daily (
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

CREATE INDEX idx_indicators_daily_symbol_date ON indicators_daily(stock_symbol, trade_date DESC);
