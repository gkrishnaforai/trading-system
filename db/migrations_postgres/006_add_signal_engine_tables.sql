-- Signal Engine tables

CREATE TABLE IF NOT EXISTS stock_signals_snapshots (
  id BIGSERIAL PRIMARY KEY,
  stock_symbol TEXT NOT NULL,
  signal_date DATE NOT NULL,
  engine_name TEXT NOT NULL,

  signal TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  position_size_pct DOUBLE PRECISION NOT NULL,
  timeframe TEXT NOT NULL,

  entry_price_range JSONB,
  stop_loss DOUBLE PRECISION,
  take_profit JSONB,

  consensus_signal TEXT,
  consensus_confidence DOUBLE PRECISION,
  recommended_engine TEXT,
  conflicts JSONB,

  reasoning JSONB NOT NULL,
  metadata JSONB,

  generated_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(stock_symbol, signal_date, engine_name)
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol_date ON stock_signals_snapshots(stock_symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_engine_date ON stock_signals_snapshots(engine_name, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_signals_confidence ON stock_signals_snapshots(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_signals_timeframe ON stock_signals_snapshots(timeframe, signal_date DESC);


CREATE TABLE IF NOT EXISTS signal_screener_cache (
  id BIGSERIAL PRIMARY KEY,
  screener_name TEXT NOT NULL,
  stock_symbol TEXT NOT NULL,

  signal TEXT NOT NULL,
  confidence DOUBLE PRECISION NOT NULL,
  engine TEXT NOT NULL,
  timeframe TEXT NOT NULL,

  rank_score DOUBLE PRECISION NOT NULL DEFAULT 0,
  sector TEXT,
  market_cap BIGINT,

  snapshot_date DATE NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(screener_name, stock_symbol, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_screener_name_date ON signal_screener_cache(screener_name, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_screener_rank ON signal_screener_cache(screener_name, rank_score DESC);


CREATE TABLE IF NOT EXISTS blog_content_metadata (
  id BIGSERIAL PRIMARY KEY,
  stock_symbol TEXT,
  blog_tier TEXT NOT NULL,

  title TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  summary TEXT,
  full_content TEXT NOT NULL,

  signal TEXT,
  confidence DOUBLE PRECISION,
  engines_used JSONB,

  publish_date DATE NOT NULL,
  view_count INTEGER NOT NULL DEFAULT 0,
  conversion_count INTEGER NOT NULL DEFAULT 0,

  meta_description TEXT,
  keywords TEXT[],

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_blog_tier_date ON blog_content_metadata(blog_tier, publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_blog_symbol_date ON blog_content_metadata(stock_symbol, publish_date DESC);


CREATE TABLE IF NOT EXISTS macro_market_data (
  data_date DATE PRIMARY KEY,

  nasdaq_close DOUBLE PRECISION,
  nasdaq_sma50 DOUBLE PRECISION,
  nasdaq_sma200 DOUBLE PRECISION,
  sp500_close DOUBLE PRECISION,

  vix_close DOUBLE PRECISION,
  vix_sma10 DOUBLE PRECISION,

  fed_funds_rate DOUBLE PRECISION,
  treasury_10y DOUBLE PRECISION,
  treasury_2y DOUBLE PRECISION,
  yield_curve_spread DOUBLE PRECISION,

  sp500_above_50d_pct DOUBLE PRECISION,
  sp500_above_200d_pct DOUBLE PRECISION,
  advance_decline_line DOUBLE PRECISION,
  new_highs INTEGER,
  new_lows INTEGER,

  es_futures_close DOUBLE PRECISION,
  nq_futures_close DOUBLE PRECISION,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_macro_date ON macro_market_data(data_date DESC);


CREATE TABLE IF NOT EXISTS sector_benchmarks (
  sector_name TEXT PRIMARY KEY,

  margin_min DOUBLE PRECISION NOT NULL,
  margin_median DOUBLE PRECISION NOT NULL,
  margin_excellent DOUBLE PRECISION NOT NULL,

  pe_low DOUBLE PRECISION NOT NULL,
  pe_median DOUBLE PRECISION NOT NULL,
  pe_high DOUBLE PRECISION NOT NULL,

  growth_min DOUBLE PRECISION NOT NULL,
  growth_strong DOUBLE PRECISION NOT NULL,

  margin_weight DOUBLE PRECISION NOT NULL DEFAULT 0.3,
  growth_weight DOUBLE PRECISION NOT NULL DEFAULT 0.4,
  valuation_weight DOUBLE PRECISION NOT NULL DEFAULT 0.3,

  last_updated DATE NOT NULL DEFAULT CURRENT_DATE,
  data_source TEXT
);

-- Seed minimal sector benchmarks
INSERT INTO sector_benchmarks (
  sector_name, margin_min, margin_median, margin_excellent,
  pe_low, pe_median, pe_high,
  growth_min, growth_strong,
  margin_weight, growth_weight, valuation_weight,
  data_source
) VALUES
  ('technology-software', 0.15, 0.22, 0.30, 20, 35, 60, 0.15, 0.40, 0.3, 0.4, 0.3, 'seed'),
  ('technology-semiconductors', 0.20, 0.28, 0.35, 15, 22, 30, 0.10, 0.30, 0.4, 0.3, 0.3, 'seed'),
  ('finance', 0.25, 0.35, 0.45, 8, 12, 18, 0.05, 0.15, 0.5, 0.2, 0.3, 'seed'),
  ('retail', 0.03, 0.07, 0.12, 10, 16, 25, 0.05, 0.20, 0.3, 0.4, 0.3, 'seed'),
  ('healthcare', 0.10, 0.18, 0.28, 15, 25, 40, 0.08, 0.25, 0.3, 0.4, 0.3, 'seed'),
  ('energy', 0.05, 0.12, 0.20, 8, 15, 25, 0.00, 0.15, 0.4, 0.2, 0.4, 'seed')
ON CONFLICT (sector_name) DO NOTHING;
