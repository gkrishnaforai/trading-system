-- Reset public schema (development only)
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO trading;
GRANT ALL ON SCHEMA public TO public;

SET search_path TO public;

-- Shared updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS '
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
' LANGUAGE plpgsql;

-- Core: users
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  subscription_level TEXT NOT NULL DEFAULT 'basic' CHECK (subscription_level IN ('basic', 'pro', 'elite')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Stocks: master registry
CREATE TABLE stocks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol VARCHAR(10) UNIQUE NOT NULL,
  exchange VARCHAR(10),
  company_name TEXT,
  sector VARCHAR(50),
  industry VARCHAR(100),
  country VARCHAR(10),
  currency VARCHAR(5),
  market_cap BIGINT,
  shares_outstanding BIGINT,
  float_shares BIGINT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stocks_symbol ON stocks(symbol);
CREATE INDEX idx_stocks_sector ON stocks(sector);
CREATE INDEX idx_stocks_industry ON stocks(industry);
CREATE INDEX idx_stocks_active ON stocks(is_active);

CREATE TRIGGER trg_stocks_updated_at
BEFORE UPDATE ON stocks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Stock financials
CREATE TABLE stock_financials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  period_type VARCHAR(10) NOT NULL CHECK (period_type IN ('quarterly', 'annual')),
  fiscal_period DATE NOT NULL,
  revenue BIGINT,
  gross_profit BIGINT,
  operating_income BIGINT,
  net_income BIGINT,
  eps NUMERIC(10,4),
  fcf BIGINT,
  capex BIGINT,
  gross_margin NUMERIC(6,4),
  operating_margin NUMERIC(6,4),
  net_margin NUMERIC(6,4),
  roe NUMERIC(6,4),
  roic NUMERIC(6,4),
  debt_to_equity NUMERIC(6,4),
  current_ratio NUMERIC(6,4),
  source VARCHAR(50),
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (stock_id, period_type, fiscal_period, source)
);

CREATE INDEX idx_stock_financials_stock_period ON stock_financials(stock_id, fiscal_period DESC);
CREATE INDEX idx_stock_financials_period_type ON stock_financials(period_type, fiscal_period DESC);

-- Stock market metrics (daily) - derived from OHLCV with indicators
CREATE TABLE stock_market_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  open_price NUMERIC(12,4),
  high_price NUMERIC(12,4),
  low_price NUMERIC(12,4),
  close_price NUMERIC(12,4),
  adj_close_price NUMERIC(12,4),
  volume BIGINT,
  avg_volume_30d BIGINT,
  dollar_volume BIGINT,
  volatility_30d NUMERIC(8,6),
  atr_14 NUMERIC(12,6),
  source VARCHAR(50),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (stock_id, date, source)
);

CREATE INDEX idx_stock_market_metrics_stock_date ON stock_market_metrics(stock_id, date DESC);
CREATE INDEX idx_stock_market_metrics_date ON stock_market_metrics(date DESC);

CREATE TRIGGER trg_stock_market_metrics_updated_at
BEFORE UPDATE ON stock_market_metrics
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Stock technical indicators (daily)
CREATE TABLE stock_technical_indicators (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  sma_20 NUMERIC(12,4),
  sma_50 NUMERIC(12,4),
  sma_200 NUMERIC(12,4),
  ema_12 NUMERIC(12,4),
  ema_26 NUMERIC(12,4),
  rsi_14 NUMERIC(8,4),
  macd NUMERIC(12,6),
  macd_signal NUMERIC(12,6),
  macd_histogram NUMERIC(12,6),
  bollinger_upper NUMERIC(12,4),
  bollinger_middle NUMERIC(12,4),
  bollinger_lower NUMERIC(12,4),
  stoch_k NUMERIC(8,4),
  stoch_d NUMERIC(8,4),
  atr_14 NUMERIC(12,6),
  adx NUMERIC(8,4),
  cci NUMERIC(8,4),
  roc NUMERIC(8,4),
  williams_r NUMERIC(8,4),
  source VARCHAR(50),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (stock_id, date, source)
);

CREATE INDEX idx_stock_technical_indicators_stock_date ON stock_technical_indicators(stock_id, date DESC);
CREATE INDEX idx_stock_technical_indicators_date ON stock_technical_indicators(date DESC);

CREATE TRIGGER trg_stock_technical_indicators_updated_at
BEFORE UPDATE ON stock_technical_indicators
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Stock derived metrics
CREATE TABLE stock_derived_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  revenue_growth_yoy NUMERIC(8,6),
  revenue_growth_acceleration NUMERIC(8,6),
  gross_margin_trend NUMERIC(8,6),
  operating_margin_trend NUMERIC(8,6),
  growth_score NUMERIC(8,6),
  quality_score NUMERIC(8,6),
  risk_score NUMERIC(8,6),
  sector_percentile JSONB,
  liquidity_tier VARCHAR(20),
  source VARCHAR(50),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (stock_id, date, source)
);

CREATE INDEX idx_stock_derived_metrics_stock_date ON stock_derived_metrics(stock_id, date DESC);
CREATE INDEX idx_stock_derived_metrics_date ON stock_derived_metrics(date DESC);

-- Sector daily benchmarks
CREATE TABLE sector_daily_metrics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL,
  universe_id TEXT NOT NULL,
  sector_schema TEXT NOT NULL,
  sector_key TEXT NOT NULL,
  median_revenue_yoy_growth NUMERIC(8,6),
  median_operating_margin NUMERIC(8,6),
  p75_operating_margin NUMERIC(8,6),
  median_pe NUMERIC(12,6),
  median_ps NUMERIC(12,6),
  median_pb NUMERIC(12,6),
  stock_count INTEGER,
  valid_pe_count INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (date, universe_id, sector_schema, sector_key)
);

CREATE INDEX idx_sector_daily_metrics_key ON sector_daily_metrics(sector_key, date DESC);
CREATE INDEX idx_sector_daily_metrics_universe ON sector_daily_metrics(universe_id, date DESC);

-- Portfolios
CREATE TABLE portfolios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  base_currency VARCHAR(5) DEFAULT 'USD',
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  is_archived BOOLEAN NOT NULL DEFAULT FALSE,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolios_user ON portfolios(user_id, is_archived, is_default);

CREATE TRIGGER trg_portfolios_updated_at
BEFORE UPDATE ON portfolios
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE portfolio_positions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE RESTRICT,
  quantity NUMERIC(14,4) NOT NULL,
  avg_price NUMERIC(12,4) NOT NULL,
  opened_at DATE,
  current_price NUMERIC(12,4),
  current_value NUMERIC(18,4),
  unrealized_gain_loss NUMERIC(18,4),
  unrealized_gain_loss_percent NUMERIC(12,6),
  last_valued_at TIMESTAMPTZ,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (portfolio_id, stock_id)
);

CREATE INDEX idx_portfolio_positions_portfolio ON portfolio_positions(portfolio_id);
CREATE INDEX idx_portfolio_positions_stock ON portfolio_positions(stock_id);

CREATE TRIGGER trg_portfolio_positions_updated_at
BEFORE UPDATE ON portfolio_positions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Watchlists
CREATE TABLE watchlists (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  is_archived BOOLEAN NOT NULL DEFAULT FALSE,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_watchlists_user ON watchlists(user_id, is_archived, is_default);

CREATE TRIGGER trg_watchlists_updated_at
BEFORE UPDATE ON watchlists
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE watchlist_stocks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  watchlist_id UUID NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE RESTRICT,
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (watchlist_id, stock_id)
);

CREATE INDEX idx_watchlist_stocks_watchlist ON watchlist_stocks(watchlist_id);
CREATE INDEX idx_watchlist_stocks_stock ON watchlist_stocks(stock_id);

CREATE TRIGGER trg_watchlist_stocks_updated_at
BEFORE UPDATE ON watchlist_stocks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Stock signals
CREATE TABLE stock_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  engine_name VARCHAR(50) NOT NULL,
  engine_version VARCHAR(20),
  engine_tier VARCHAR(10),
  signal VARCHAR(10) NOT NULL,
  confidence NUMERIC(6,4),
  fair_value NUMERIC(12,4),
  upside_pct NUMERIC(12,6),
  reasoning JSONB,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stock_signals_stock_engine_created ON stock_signals(stock_id, engine_name, created_at DESC);
CREATE INDEX idx_stock_signals_created ON stock_signals(created_at DESC);

-- AI insights overlay
CREATE TABLE stock_ai_insights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  ai_exposure_score NUMERIC(8,4),
  explanation TEXT,
  confidence_level VARCHAR(10),
  raw_analysis JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (stock_id, date)
);

CREATE INDEX idx_stock_ai_insights_stock_date ON stock_ai_insights(stock_id, date DESC);

-- News
CREATE TABLE stock_news (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stock_id UUID NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  published_at TIMESTAMPTZ,
  title TEXT NOT NULL,
  publisher TEXT,
  url TEXT,
  sentiment_score NUMERIC(8,6),
  related_symbols JSONB,
  source VARCHAR(50),
  raw_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stock_news_stock_published ON stock_news(stock_id, published_at DESC);

-- Blog content
CREATE TABLE blog_posts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  stock_id UUID REFERENCES stocks(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  slug TEXT UNIQUE,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'published' CHECK (status IN ('draft', 'published', 'archived')),
  tags JSONB,
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_blog_posts_stock_published ON blog_posts(stock_id, published_at DESC);
CREATE INDEX idx_blog_posts_status ON blog_posts(status, published_at DESC);

CREATE TRIGGER trg_blog_posts_updated_at
BEFORE UPDATE ON blog_posts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Recreate migrations tracking table after schema reset
CREATE TABLE IF NOT EXISTS public.schema_migrations (
  migration_name TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
