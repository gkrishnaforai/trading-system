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


CREATE TABLE IF NOT EXISTS fundamentals_snapshots (
  stock_symbol TEXT NOT NULL,
  as_of_date DATE NOT NULL,
  source TEXT,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol_date ON fundamentals_snapshots(stock_symbol, as_of_date DESC);


CREATE TABLE IF NOT EXISTS stock_news (
  news_id TEXT PRIMARY KEY,
  stock_symbol TEXT NOT NULL,
  title TEXT NOT NULL,
  publisher TEXT,
  link TEXT,
  published_at TIMESTAMPTZ,
  sentiment_score DOUBLE PRECISION,
  related_symbols JSONB,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE stock_news
  ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_stock_news_symbol_date ON stock_news(stock_symbol, published_at DESC);


CREATE TABLE IF NOT EXISTS earnings_data (
  earnings_id TEXT PRIMARY KEY,
  stock_symbol TEXT NOT NULL,
  earnings_date DATE NOT NULL,
  eps_estimate DOUBLE PRECISION,
  eps_actual DOUBLE PRECISION,
  revenue_estimate DOUBLE PRECISION,
  revenue_actual DOUBLE PRECISION,
  surprise_percentage DOUBLE PRECISION,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (stock_symbol, earnings_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_symbol_date ON earnings_data(stock_symbol, earnings_date DESC);


CREATE TABLE IF NOT EXISTS industry_peers (
  stock_symbol TEXT NOT NULL,
  peer_symbol TEXT NOT NULL,
  sector TEXT,
  industry TEXT,
  peer_name TEXT,
  peer_market_cap DOUBLE PRECISION,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, peer_symbol)
);

CREATE INDEX IF NOT EXISTS idx_industry_peers_symbol ON industry_peers(stock_symbol);


CREATE TABLE IF NOT EXISTS data_validation_reports (
  report_id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  data_type TEXT NOT NULL,
  validation_timestamp TIMESTAMPTZ NOT NULL,
  report_json JSONB NOT NULL,
  overall_status TEXT NOT NULL,
  critical_issues INTEGER DEFAULT 0,
  warnings INTEGER DEFAULT 0,
  rows_dropped INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_symbol_type ON data_validation_reports(symbol, data_type);
CREATE INDEX IF NOT EXISTS idx_validation_timestamp ON data_validation_reports(validation_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_validation_status ON data_validation_reports(overall_status);


CREATE TABLE IF NOT EXISTS data_fetch_audit (
  audit_id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  fetch_type TEXT NOT NULL,
  fetch_mode TEXT NOT NULL,
  fetch_timestamp TIMESTAMPTZ NOT NULL,
  data_source TEXT,
  rows_fetched INTEGER DEFAULT 0,
  rows_saved INTEGER DEFAULT 0,
  fetch_duration_ms INTEGER,
  success BOOLEAN NOT NULL,
  error_message TEXT,
  validation_report_id TEXT REFERENCES data_validation_reports(report_id) ON DELETE SET NULL,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fetch_audit_symbol ON data_fetch_audit(symbol, fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_audit_type ON data_fetch_audit(fetch_type, fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_audit_success ON data_fetch_audit(success, fetch_timestamp DESC);
