-- resilience engine scorecard journal + fact-check validator results
CREATE TABLE IF NOT EXISTS company_resilience_scores (
  symbol TEXT NOT NULL,
  as_of DATE NOT NULL,
  formula_version INT NOT NULL,
  payload JSONB NOT NULL,
  ai_score NUMERIC, health_score NUMERIC, tape_score NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, as_of));
CREATE INDEX IF NOT EXISTS crs_asof ON company_resilience_scores (as_of DESC);

CREATE TABLE IF NOT EXISTS symbol_fact_checks (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL, field TEXT NOT NULL, verdict TEXT NOT NULL,
  evidence JSONB,
  checked_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS sfc_sym_field
  ON symbol_fact_checks (symbol, field, checked_at DESC);
