-- Persisted derived fundamental-expectation momentum assessments.
CREATE TABLE IF NOT EXISTS fundamental_momentum_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(32) NOT NULL,
    as_of_date DATE NOT NULL,
    score NUMERIC(8,3),
    label VARCHAR(32) NOT NULL,
    eps_revision_14d NUMERIC(12,8),
    eps_revision_30d NUMERIC(12,8),
    revenue_revision_30d NUMERIC(12,8),
    growth_acceleration NUMERIC(12,8),
    revision_breadth NUMERIC(12,8),
    net_revision_breadth NUMERIC(12,8),
    estimate_dispersion NUMERIC(12,8),
    guidance_direction VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    coverage NUMERIC(8,4) NOT NULL DEFAULT 0,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    source VARCHAR(128) NOT NULL DEFAULT 'deterministic',
    rules_version VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, as_of_date, rules_version)
);

CREATE INDEX IF NOT EXISTS idx_fundamental_momentum_symbol_date
    ON fundamental_momentum_assessments(symbol, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_fundamental_momentum_label_score
    ON fundamental_momentum_assessments(label, score DESC);
