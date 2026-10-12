CREATE TABLE IF NOT EXISTS macro_series_points (
  series_id TEXT NOT NULL,
  observation_date DATE NOT NULL,
  value NUMERIC,
  source TEXT NOT NULL DEFAULT 'fred',
  retrieved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (series_id, observation_date)
);

CREATE INDEX IF NOT EXISTS idx_macro_series_points_series_date
  ON macro_series_points(series_id, observation_date);

CREATE TABLE IF NOT EXISTS macro_snapshots (
  id BIGSERIAL PRIMARY KEY,
  as_of_date DATE NOT NULL UNIQUE,
  module_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
  overall_score NUMERIC,
  regime_probs JSONB NOT NULL DEFAULT '{}'::jsonb,
  portfolio_alloc JSONB NOT NULL DEFAULT '{}'::jsonb,
  signals JSONB NOT NULL DEFAULT '{}'::jsonb,
  inputs_used JSONB NOT NULL DEFAULT '{}'::jsonb,
  is_month_end BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_macro_snapshots_as_of_date
  ON macro_snapshots(as_of_date);

CREATE INDEX IF NOT EXISTS idx_macro_snapshots_is_month_end
  ON macro_snapshots(is_month_end, as_of_date);
