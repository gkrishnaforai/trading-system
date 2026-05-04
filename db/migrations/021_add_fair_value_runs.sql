CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS fair_value_methods (
    method_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fair_value_method_versions (
    method_version_id TEXT PRIMARY KEY,
    method_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    definition_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(method_key, version),
    FOREIGN KEY (method_key) REFERENCES fair_value_methods(method_key) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS fair_value_runs (
    run_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    as_of TIMESTAMP NOT NULL,
    current_price DOUBLE PRECISION,
    fair_value DOUBLE PRECISION,
    valuation_ratio DOUBLE PRECISION,
    undervaluation_pct DOUBLE PRECISION,
    valuation_rating TEXT,
    quality_score DOUBLE PRECISION,
    valuation_metrics JSONB,
    fundamentals JSONB,
    individual_valuations JSONB,
    model_version TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fair_value_method_results (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    method_key TEXT NOT NULL,
    method_version_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,
    status TEXT,
    fair_price DOUBLE PRECISION,
    upside_pct DOUBLE PRECISION,
    metrics_json JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES fair_value_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY (method_key) REFERENCES fair_value_methods(method_key) ON DELETE RESTRICT,
    FOREIGN KEY (method_version_id) REFERENCES fair_value_method_versions(method_version_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_fair_value_runs_symbol_as_of ON fair_value_runs(symbol, as_of DESC);
CREATE INDEX IF NOT EXISTS idx_fair_value_runs_created_at ON fair_value_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fair_value_method_results_run ON fair_value_method_results(run_id);
CREATE INDEX IF NOT EXISTS idx_fair_value_method_results_method ON fair_value_method_results(method_key, created_at DESC);

INSERT INTO fair_value_methods(method_key, name, description)
VALUES
    ('peg_legacy', 'PEG Method (Legacy)', 'PEG-based fair value using trailing EPS growth and industry avg PEG'),
    ('peg_rule_of_40_forward_cagr', 'PEG Rule-of-40 (Forward CAGR)', 'PEG-based fair value using forward EPS CAGR and Rule-of-40 target PEG'),
    ('pe_forward', 'P/E Method (Forward)', 'Forward EPS times adjusted industry P/E'),
    ('dcf_simple', 'DCF Method (Simple)', 'Simplified DCF using FCF projections, discount rate, and terminal value'),
    ('weighted_blend', 'Weighted Fair Value', 'Weighted blend of method fair values based on data quality and heuristics')
ON CONFLICT (method_key) DO NOTHING;

INSERT INTO fair_value_method_versions(method_version_id, method_key, version, is_active, definition_json)
VALUES
    (uuid_generate_v4()::text, 'peg_legacy', 1, true, '{"inputs":["eps_ttm","eps_yoy_growth","industry_avg_peg"],"caps":{"fair_pe_cap":40},"notes":"P/E = industry_avg_peg * growth_pct"}'::jsonb),
    (uuid_generate_v4()::text, 'peg_rule_of_40_forward_cagr', 1, true, '{"inputs":["forward_eps_series","revenue_yoy_growth_pct","net_margin_pct"],"caps":{"cagr_cap":0.70,"target_pe_cap":60},"window_policy":"preferred_3y_else_longest"}'::jsonb),
    (uuid_generate_v4()::text, 'pe_forward', 1, true, '{"inputs":["eps_forward","industry_avg_pe","eps_yoy_growth"],"notes":"adjusted_pe = industry_pe*(1+min(eps_growth/10,1.5))"}'::jsonb),
    (uuid_generate_v4()::text, 'dcf_simple', 1, true, '{"inputs":["free_cash_flow","eps_yoy_growth","market_cap","current_price"],"assumptions":{"discount_rate":0.10,"terminal_growth":0.03,"projection_years":5,"growth_cap":0.20}}'::jsonb),
    (uuid_generate_v4()::text, 'weighted_blend', 1, true, '{"inputs":["peg_legacy","peg_rule_of_40_forward_cagr","pe_forward","dcf_simple"],"notes":"weights determined by _weight_valuations"}'::jsonb)
ON CONFLICT (method_key, version) DO NOTHING;
