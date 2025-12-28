-- Baseline schema (PostgreSQL/Supabase)
-- Clean-slate, DRY schema. This migration is intended to be the single source of truth.

BEGIN;

-- Reset public schema (NOT for production; intended for local/dev resets)
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO trading;
GRANT ALL ON SCHEMA public TO public;

SET search_path TO public;

-- Shared updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==========================
-- Core: users / portfolios
-- ==========================
CREATE TABLE users (
  user_id TEXT PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  subscription_level TEXT NOT NULL DEFAULT 'basic' CHECK (subscription_level IN ('basic', 'pro', 'elite')),
  preferred_strategy TEXT DEFAULT 'technical' CHECK (preferred_strategy IN ('technical', 'hybrid_llm', 'custom')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE portfolios (
  portfolio_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  portfolio_name TEXT NOT NULL,
  notes TEXT,
  strategy_name TEXT,

  portfolio_type TEXT CHECK (portfolio_type IN ('long_term', 'swing', 'day_trading', 'options', 'crypto', 'mixed')) DEFAULT 'mixed',
  currency TEXT DEFAULT 'USD',
  benchmark_symbol TEXT,
  target_allocation JSONB,
  risk_tolerance TEXT CHECK (risk_tolerance IN ('conservative', 'moderate', 'aggressive')) DEFAULT 'moderate',
  investment_horizon TEXT CHECK (investment_horizon IN ('short_term', 'medium_term', 'long_term')) DEFAULT 'medium_term',
  is_taxable BOOLEAN DEFAULT TRUE,
  tax_strategy TEXT,
  rebalancing_frequency TEXT CHECK (rebalancing_frequency IN ('daily', 'weekly', 'monthly', 'quarterly', 'annually', 'manual')) DEFAULT 'manual',
  last_rebalanced DATE,
  color_code TEXT,
  is_archived BOOLEAN DEFAULT FALSE,
  metadata JSONB,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_portfolios_user_id ON portfolios(user_id);
CREATE INDEX idx_portfolios_archived ON portfolios(user_id, is_archived);

CREATE TRIGGER trg_portfolios_updated_at
BEFORE UPDATE ON portfolios
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE holdings (
  holding_id TEXT PRIMARY KEY,
  portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
  stock_symbol TEXT NOT NULL,
  quantity DOUBLE PRECISION NOT NULL,
  avg_entry_price DOUBLE PRECISION NOT NULL,
  position_type TEXT NOT NULL CHECK (position_type IN ('long', 'short', 'call_option', 'put_option')),
  strategy_tag TEXT,
  purchase_date DATE NOT NULL,
  notes TEXT,

  -- Trader/analyst fields (nullable, computed/cached by app)
  current_price DOUBLE PRECISION,
  current_value DOUBLE PRECISION,
  cost_basis DOUBLE PRECISION,
  unrealized_gain_loss DOUBLE PRECISION,
  unrealized_gain_loss_percent DOUBLE PRECISION,
  realized_gain_loss DOUBLE PRECISION DEFAULT 0,
  exit_price DOUBLE PRECISION,
  exit_date DATE,
  commission DOUBLE PRECISION DEFAULT 0,
  tax_lot_id TEXT,
  cost_basis_method TEXT CHECK (cost_basis_method IN ('FIFO', 'LIFO', 'average', 'specific_lot')) DEFAULT 'average',
  sector TEXT,
  industry TEXT,
  market_cap_category TEXT CHECK (market_cap_category IN ('mega', 'large', 'mid', 'small', 'micro')),
  dividend_yield DOUBLE PRECISION,
  target_price DOUBLE PRECISION,
  stop_loss_price DOUBLE PRECISION,
  take_profit_price DOUBLE PRECISION,
  allocation_percent DOUBLE PRECISION,
  target_allocation_percent DOUBLE PRECISION,
  last_updated_price TIMESTAMPTZ,
  is_closed BOOLEAN DEFAULT FALSE,
  closed_reason TEXT,
  metadata JSONB,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_holdings_portfolio_id ON holdings(portfolio_id);
CREATE INDEX idx_holdings_symbol ON holdings(stock_symbol);

CREATE TRIGGER trg_holdings_updated_at
BEFORE UPDATE ON holdings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ==========================
-- Watchlists
-- ==========================
CREATE TABLE watchlists (
  watchlist_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  watchlist_name TEXT NOT NULL,
  description TEXT,
  tags TEXT,
  is_default BOOLEAN DEFAULT FALSE,
  subscription_level_required TEXT CHECK (subscription_level_required IN ('basic', 'pro', 'elite')) DEFAULT 'basic',

  color_code TEXT,
  sort_order INTEGER DEFAULT 0,
  view_preferences JSONB,
  is_archived BOOLEAN DEFAULT FALSE,
  metadata JSONB,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_watchlists_user_id ON watchlists(user_id);
CREATE INDEX idx_watchlists_default ON watchlists(user_id, is_default);

CREATE TRIGGER trg_watchlists_updated_at
BEFORE UPDATE ON watchlists
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE watchlist_items (
  item_id TEXT PRIMARY KEY,
  watchlist_id TEXT NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
  stock_symbol TEXT NOT NULL,
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notes TEXT,
  priority INTEGER DEFAULT 0,
  tags TEXT,
  alert_config JSONB,

  price_when_added DOUBLE PRECISION,
  target_price DOUBLE PRECISION,
  target_date DATE,
  watch_reason TEXT,
  analyst_rating TEXT CHECK (analyst_rating IN ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')),
  analyst_price_target DOUBLE PRECISION,
  current_price DOUBLE PRECISION,
  price_change_since_added DOUBLE PRECISION,
  price_change_percent_since_added DOUBLE PRECISION,
  sector TEXT,
  industry TEXT,
  market_cap_category TEXT CHECK (market_cap_category IN ('mega', 'large', 'mid', 'small', 'micro')),
  dividend_yield DOUBLE PRECISION,
  earnings_date DATE,
  last_updated_price TIMESTAMPTZ,
  metadata JSONB,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (watchlist_id, stock_symbol)
);

CREATE INDEX idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
CREATE INDEX idx_watchlist_items_symbol ON watchlist_items(stock_symbol);
CREATE INDEX idx_watchlist_items_priority ON watchlist_items(watchlist_id, priority DESC);

CREATE TRIGGER trg_watchlist_items_updated_at
BEFORE UPDATE ON watchlist_items
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ==========================
-- Market data (split by granularity)
-- ==========================
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

CREATE INDEX idx_raw_daily_symbol_date ON raw_market_data_daily(stock_symbol, trade_date DESC);
CREATE INDEX idx_raw_daily_date ON raw_market_data_daily(trade_date DESC);

CREATE TRIGGER trg_raw_market_data_daily_updated_at
BEFORE UPDATE ON raw_market_data_daily
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE raw_market_data_intraday (
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

CREATE INDEX idx_raw_intraday_symbol_interval_ts ON raw_market_data_intraday(stock_symbol, interval, ts DESC);
CREATE INDEX idx_raw_intraday_ts ON raw_market_data_intraday(ts DESC);

CREATE TRIGGER trg_raw_market_data_intraday_updated_at
BEFORE UPDATE ON raw_market_data_intraday
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ==========================
-- Indicators (split by granularity)
-- ==========================
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

  signal TEXT CHECK (signal IN ('buy', 'sell', 'hold')),
  confidence_score DOUBLE PRECISION,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, trade_date)
);

CREATE INDEX idx_indicators_daily_symbol_date ON indicators_daily(stock_symbol, trade_date DESC);
CREATE INDEX idx_indicators_daily_signal_date ON indicators_daily(signal, trade_date DESC);

CREATE TRIGGER trg_indicators_daily_updated_at
BEFORE UPDATE ON indicators_daily
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE indicators_intraday (
  stock_symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  interval TEXT NOT NULL,

  ema_9 DOUBLE PRECISION,
  ema_21 DOUBLE PRECISION,
  vwap DOUBLE PRECISION,
  rsi_14 DOUBLE PRECISION,
  macd DOUBLE PRECISION,

  signal TEXT,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, ts, interval)
);

CREATE INDEX idx_indicators_intraday_symbol_interval_ts ON indicators_intraday(stock_symbol, interval, ts DESC);

CREATE TRIGGER trg_indicators_intraday_updated_at
BEFORE UPDATE ON indicators_intraday
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ==========================
-- Provider-agnostic ingestion state (cursor)
-- ==========================
CREATE TABLE data_ingestion_state (
  stock_symbol TEXT NOT NULL,
  dataset TEXT NOT NULL,
  interval TEXT,
  source TEXT,

  historical_start_date DATE,
  historical_end_date DATE,

  cursor_date DATE,
  cursor_ts TIMESTAMPTZ,

  last_attempt_at TIMESTAMPTZ,
  last_success_at TIMESTAMPTZ,

  status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle', 'running', 'success', 'failed')),
  error_message TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, dataset, interval)
);

CREATE INDEX idx_ingestion_state_dataset_status ON data_ingestion_state(dataset, status);
CREATE INDEX idx_ingestion_state_symbol_dataset ON data_ingestion_state(stock_symbol, dataset);

CREATE TRIGGER trg_data_ingestion_state_updated_at
BEFORE UPDATE ON data_ingestion_state
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ==========================
-- Fundamentals / news / earnings (provider-agnostic)
-- ==========================
CREATE TABLE fundamentals_snapshots (
  stock_symbol TEXT NOT NULL,
  as_of_date DATE NOT NULL,
  source TEXT,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, as_of_date)
);

CREATE INDEX idx_fundamentals_symbol_date ON fundamentals_snapshots(stock_symbol, as_of_date DESC);

CREATE TRIGGER trg_fundamentals_snapshots_updated_at
BEFORE UPDATE ON fundamentals_snapshots
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE stock_news (
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

CREATE INDEX idx_stock_news_symbol_date ON stock_news(stock_symbol, published_at DESC);

CREATE TRIGGER trg_stock_news_updated_at
BEFORE UPDATE ON stock_news
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE earnings_data (
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

CREATE INDEX idx_earnings_symbol_date ON earnings_data(stock_symbol, earnings_date DESC);

CREATE TRIGGER trg_earnings_data_updated_at
BEFORE UPDATE ON earnings_data
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE industry_peers (
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

CREATE INDEX idx_industry_peers_symbol ON industry_peers(stock_symbol);

CREATE TRIGGER trg_industry_peers_updated_at
BEFORE UPDATE ON industry_peers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ==========================
-- Alerts (pluggable)
-- ==========================
CREATE TABLE alert_types (
  alert_type_id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  description TEXT,
  plugin_name TEXT NOT NULL,
  config_schema JSONB,
  enabled BOOLEAN DEFAULT TRUE,
  subscription_level_required TEXT CHECK (subscription_level_required IN ('basic', 'pro', 'elite')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_alert_types_updated_at
BEFORE UPDATE ON alert_types
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE alerts (
  alert_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  portfolio_id TEXT REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
  stock_symbol TEXT,
  alert_type_id TEXT NOT NULL REFERENCES alert_types(alert_type_id),
  name TEXT NOT NULL,
  enabled BOOLEAN DEFAULT TRUE,
  config JSONB NOT NULL,
  notification_channels TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK ((portfolio_id IS NOT NULL) OR (stock_symbol IS NOT NULL))
);

CREATE INDEX idx_alerts_user_id ON alerts(user_id);
CREATE INDEX idx_alerts_portfolio_id ON alerts(portfolio_id);
CREATE INDEX idx_alerts_stock_symbol ON alerts(stock_symbol);
CREATE INDEX idx_alerts_enabled ON alerts(enabled);

CREATE TRIGGER trg_alerts_updated_at
BEFORE UPDATE ON alerts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE alert_notifications (
  notification_id TEXT PRIMARY KEY,
  alert_id TEXT NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  portfolio_id TEXT REFERENCES portfolios(portfolio_id) ON DELETE SET NULL,
  stock_symbol TEXT,
  alert_type_id TEXT NOT NULL REFERENCES alert_types(alert_type_id),
  message TEXT NOT NULL,
  severity TEXT CHECK (severity IN ('info', 'warning', 'critical')) DEFAULT 'info',
  channel TEXT NOT NULL CHECK (channel IN ('email', 'sms', 'push', 'webhook')),
  status TEXT CHECK (status IN ('pending', 'sent', 'failed')) DEFAULT 'pending',
  sent_at TIMESTAMPTZ,
  error_message TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alert_notifications_alert_id ON alert_notifications(alert_id);
CREATE INDEX idx_alert_notifications_user_id ON alert_notifications(user_id);
CREATE INDEX idx_alert_notifications_status ON alert_notifications(status);
CREATE INDEX idx_alert_notifications_created_at ON alert_notifications(created_at DESC);

CREATE TRIGGER trg_alert_notifications_updated_at
BEFORE UPDATE ON alert_notifications
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE notification_channels (
  channel_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  channel_type TEXT NOT NULL CHECK (channel_type IN ('email', 'sms', 'push', 'webhook')),
  address TEXT NOT NULL,
  verified BOOLEAN DEFAULT FALSE,
  enabled BOOLEAN DEFAULT TRUE,
  config JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, channel_type, address)
);

CREATE INDEX idx_notification_channels_user_id ON notification_channels(user_id);
CREATE INDEX idx_notification_channels_type ON notification_channels(channel_type);

CREATE TRIGGER trg_notification_channels_updated_at
BEFORE UPDATE ON notification_channels
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Seed default alert types
INSERT INTO alert_types (alert_type_id, name, display_name, description, plugin_name, config_schema, subscription_level_required)
VALUES
  ('price_threshold', 'price_threshold', 'Price Threshold', 'Alert when stock price crosses a threshold', 'email_alert', '{"type":"object","properties":{"threshold":{"type":"number"},"direction":{"type":"string","enum":["above","below"]}}}', 'basic'),
  ('signal_change', 'signal_change', 'Signal Change', 'Alert when trading signal changes (buy/sell/hold)', 'email_alert', '{"type":"object","properties":{"from_signal":{"type":"string"},"to_signal":{"type":"string"}}}', 'pro')
ON CONFLICT (alert_type_id) DO NOTHING;

-- ==========================
-- Content (blog) - full workflow
-- ==========================
CREATE TABLE blog_topics (
  topic_id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  topic_type TEXT NOT NULL CHECK (topic_type IN ('signal_change', 'golden_cross', 'rsi_extreme', 'earnings_proximity', 'portfolio_heavy', 'volume_spike', 'trend_reversal')),
  reason JSONB NOT NULL,
  urgency TEXT CHECK (urgency IN ('low', 'medium', 'high', 'critical')) DEFAULT 'medium',
  audience TEXT CHECK (audience IN ('basic', 'pro', 'elite', 'basic_to_pro', 'all')) DEFAULT 'basic_to_pro',
  confidence DOUBLE PRECISION DEFAULT 0.5,
  score DOUBLE PRECISION DEFAULT 0.0,
  context_data JSONB,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_blog_topics_user ON blog_topics(user_id);
CREATE INDEX idx_blog_topics_symbol ON blog_topics(symbol);
CREATE INDEX idx_blog_topics_score ON blog_topics(score DESC);

CREATE TRIGGER trg_blog_topics_updated_at
BEFORE UPDATE ON blog_topics
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE blog_drafts (
  draft_id TEXT PRIMARY KEY,
  topic_id TEXT NOT NULL REFERENCES blog_topics(topic_id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  title TEXT NOT NULL,
  meta_description TEXT,
  slug TEXT UNIQUE,
  content TEXT NOT NULL,
  tags JSONB,
  status TEXT CHECK (status IN ('draft', 'review', 'approved', 'rejected')) DEFAULT 'draft',
  generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  reviewed_at TIMESTAMPTZ,
  reviewed_by TEXT,
  review_notes TEXT,
  context_used JSONB,
  llm_metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_blog_drafts_user ON blog_drafts(user_id);
CREATE INDEX idx_blog_drafts_topic ON blog_drafts(topic_id);
CREATE INDEX idx_blog_drafts_status ON blog_drafts(status, generated_at DESC);

CREATE TRIGGER trg_blog_drafts_updated_at
BEFORE UPDATE ON blog_drafts
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE blog_published (
  published_id TEXT PRIMARY KEY,
  draft_id TEXT NOT NULL REFERENCES blog_drafts(draft_id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  title TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  content TEXT NOT NULL,
  meta_description TEXT,
  tags JSONB,
  published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  published_to JSONB NOT NULL,
  seo_data JSONB,
  view_count INTEGER DEFAULT 0,
  engagement_score DOUBLE PRECISION DEFAULT 0.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_blog_published_user ON blog_published(user_id);
CREATE INDEX idx_blog_published_symbol ON blog_published(symbol);
CREATE INDEX idx_blog_published_date ON blog_published(published_at DESC);

CREATE TRIGGER trg_blog_published_updated_at
BEFORE UPDATE ON blog_published
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE blog_publishing_config (
  config_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL UNIQUE REFERENCES users(user_id) ON DELETE CASCADE,
  auto_generate BOOLEAN DEFAULT FALSE,
  auto_publish BOOLEAN DEFAULT FALSE,
  min_topic_score DOUBLE PRECISION DEFAULT 70.0,
  publishing_destinations JSONB,
  content_preferences JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_blog_publishing_config_user ON blog_publishing_config(user_id);

CREATE TRIGGER trg_blog_publishing_config_updated_at
BEFORE UPDATE ON blog_publishing_config
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE blog_generation_audit (
  audit_id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  topic_id TEXT REFERENCES blog_topics(topic_id) ON DELETE SET NULL,
  draft_id TEXT REFERENCES blog_drafts(draft_id) ON DELETE SET NULL,

  generation_request JSONB NOT NULL,
  context_data JSONB NOT NULL,
  system_prompt TEXT,
  user_prompt TEXT,
  prompt_template TEXT,

  agent_type TEXT,
  agent_config JSONB,
  llm_provider TEXT,
  llm_model TEXT,
  llm_parameters JSONB,

  generation_result JSONB,
  generated_content TEXT,
  generation_metadata JSONB,

  status TEXT NOT NULL CHECK (status IN ('pending', 'in_progress', 'success', 'failed', 'retrying', 'cancelled')) DEFAULT 'pending',
  stage TEXT NOT NULL CHECK (stage IN ('topic_ranked', 'context_built', 'agent_invoked', 'content_generated', 'content_validated', 'draft_created', 'published', 'failed')) DEFAULT 'topic_ranked',

  error_message TEXT,
  error_details JSONB,
  retry_count INTEGER DEFAULT 0,
  max_retries INTEGER DEFAULT 3,
  last_retry_at TIMESTAMPTZ,

  can_retry BOOLEAN DEFAULT TRUE,
  retry_with_llm TEXT,
  recovery_data JSONB,

  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  correlation_id TEXT,
  parent_audit_id TEXT REFERENCES blog_generation_audit(audit_id) ON DELETE SET NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_blog_generation_audit_user ON blog_generation_audit(user_id);
CREATE INDEX idx_blog_generation_audit_topic ON blog_generation_audit(topic_id);
CREATE INDEX idx_blog_generation_audit_draft ON blog_generation_audit(draft_id);
CREATE INDEX idx_blog_generation_audit_status ON blog_generation_audit(status, stage);
CREATE INDEX idx_blog_generation_audit_correlation ON blog_generation_audit(correlation_id);
CREATE INDEX idx_blog_generation_audit_created ON blog_generation_audit(created_at DESC);

CREATE TRIGGER trg_blog_generation_audit_updated_at
BEFORE UPDATE ON blog_generation_audit
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE blog_generation_log (
  log_id BIGSERIAL PRIMARY KEY,
  audit_id TEXT NOT NULL REFERENCES blog_generation_audit(audit_id) ON DELETE CASCADE,
  user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
  topic_id TEXT REFERENCES blog_topics(topic_id) ON DELETE SET NULL,
  draft_id TEXT REFERENCES blog_drafts(draft_id) ON DELETE SET NULL,
  action TEXT NOT NULL CHECK (action IN ('topic_ranked', 'context_built', 'blog_generated', 'blog_published', 'blog_failed')),
  status TEXT CHECK (status IN ('success', 'failed', 'partial')) DEFAULT 'success',
  error_message TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_blog_generation_log_audit ON blog_generation_log(audit_id);
CREATE INDEX idx_blog_generation_log_user ON blog_generation_log(user_id);
CREATE INDEX idx_blog_generation_log_action ON blog_generation_log(action, created_at DESC);

-- ==========================
-- Workflow execution tracking (pipeline orchestration)
-- ==========================
CREATE TABLE workflow_executions (
  workflow_id TEXT PRIMARY KEY,
  workflow_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'paused', 'cancelled')),
  current_stage TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  metadata_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_workflow_status ON workflow_executions(status);
CREATE INDEX idx_workflow_type ON workflow_executions(workflow_type);
CREATE INDEX idx_workflow_created ON workflow_executions(created_at DESC);

CREATE TRIGGER trg_workflow_executions_updated_at
BEFORE UPDATE ON workflow_executions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE workflow_stage_executions (
  stage_execution_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflow_executions(workflow_id) ON DELETE CASCADE,
  stage_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  symbols_processed INTEGER DEFAULT 0,
  symbols_succeeded INTEGER DEFAULT 0,
  symbols_failed INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stage_workflow ON workflow_stage_executions(workflow_id, stage_name);
CREATE INDEX idx_stage_status ON workflow_stage_executions(status);

CREATE TRIGGER trg_workflow_stage_executions_updated_at
BEFORE UPDATE ON workflow_stage_executions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE workflow_symbol_states (
  id BIGSERIAL PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflow_executions(workflow_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'retrying')),
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (workflow_id, symbol, stage)
);

CREATE INDEX idx_symbol_workflow ON workflow_symbol_states(workflow_id, symbol);
CREATE INDEX idx_symbol_stage ON workflow_symbol_states(symbol, stage, status);

CREATE TRIGGER trg_workflow_symbol_states_updated_at
BEFORE UPDATE ON workflow_symbol_states
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE workflow_checkpoints (
  checkpoint_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflow_executions(workflow_id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  state_json JSONB NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_checkpoint_workflow ON workflow_checkpoints(workflow_id, ts DESC);

CREATE TABLE workflow_dlq (
  dlq_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflow_executions(workflow_id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  stage TEXT NOT NULL,
  error_message TEXT NOT NULL,
  error_type TEXT,
  context_json JSONB,
  retry_count INTEGER DEFAULT 0,
  resolved BOOLEAN DEFAULT FALSE,
  resolved_at TIMESTAMPTZ,
  resolved_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dlq_unresolved ON workflow_dlq(resolved, created_at DESC);
CREATE INDEX idx_dlq_symbol ON workflow_dlq(symbol, stage);

CREATE TABLE workflow_gate_results (
  gate_result_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflow_executions(workflow_id) ON DELETE CASCADE,
  stage TEXT NOT NULL,
  symbol TEXT NOT NULL,
  gate_name TEXT NOT NULL,
  passed BOOLEAN NOT NULL,
  reason TEXT,
  action TEXT,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gate_workflow ON workflow_gate_results(workflow_id, stage, symbol);

-- ==========================
-- Data quality / fetch audit
-- ==========================
CREATE TABLE data_validation_reports (
  report_id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  data_type TEXT NOT NULL,
  validation_timestamp TIMESTAMPTZ NOT NULL,
  report_json JSONB NOT NULL,
  overall_status TEXT NOT NULL CHECK (overall_status IN ('pass', 'warning', 'fail')),
  critical_issues INTEGER DEFAULT 0,
  warnings INTEGER DEFAULT 0,
  rows_dropped INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validation_symbol_type ON data_validation_reports(symbol, data_type);
CREATE INDEX idx_validation_timestamp ON data_validation_reports(validation_timestamp DESC);
CREATE INDEX idx_validation_status ON data_validation_reports(overall_status);

CREATE TABLE data_fetch_audit (
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

CREATE INDEX idx_fetch_audit_symbol ON data_fetch_audit(symbol, fetch_timestamp DESC);
CREATE INDEX idx_fetch_audit_type ON data_fetch_audit(fetch_type, fetch_timestamp DESC);
CREATE INDEX idx_fetch_audit_success ON data_fetch_audit(success, fetch_timestamp DESC);

COMMIT;
