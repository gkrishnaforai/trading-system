/*
 * Restore live tables dropped by 136_drop_dead_tables.
 * The dead-table audit was wrong: these tables are still written and
 * read by python-worker paths (doc_analyses is in the active-tier
 * universe UNION, fair_value_methods was proven live by prod INSERT
 * errors). Restored verbatim from original migration DDL, idempotent,
 * dependency-ordered (FK parents before children). Self-healing tables
 * (massive_*, trading_signals, company_profile_scores_auto) and
 * genuinely-orphaned legacy alert/consensus tables stay dropped.
 * NOTE: no line comments, quotes, or semicolons in this file. The
 * statement splitter is quote-aware but not comment-aware.
 */

CREATE TABLE IF NOT EXISTS blog_posts (
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

CREATE TABLE IF NOT EXISTS doc_analyses (
    id          bigserial PRIMARY KEY,
    symbol      text NOT NULL,
    url         text,
    title       text,
    thesis      text,
    claims      jsonb,
    dropped     jsonb,
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event_day_calls (
    id           bigserial PRIMARY KEY,
    as_of        date NOT NULL,
    event_name   text NOT NULL,
    event_kind   text NOT NULL,
    verdict      text NOT NULL,
    confidence   int,
    thesis       text,
    premarket_spy double precision,
    context      jsonb,
    judge        text,
    spy_ret_1d   double precision,
    correct      boolean,
    graded_at    timestamptz,
    probs        jsonb,
    regime_read  text,
    qqq_lean     text,
    qqq_note     text,
    qqq_ret_1d   double precision,
    qqq_correct  boolean,
    print_data   jsonb,
    brier        double precision,
    debrief      text,
    created_at   timestamptz DEFAULT now(),
    UNIQUE (as_of, event_kind)
);

CREATE TABLE IF NOT EXISTS growth_forecast_snapshots (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    as_of           date NOT NULL,
    model_version   text NOT NULL,

    fwd_eps_avg     numeric,
    fwd_rev_avg     numeric,
    est_revision_pct numeric,
    rev_breadth_30d int,
    revision_score  numeric,
    revision_grade  text,
    num_analysts    int,

    fundamental_state text,
    priced_status   text,
    emerging_growth text,
    fwd_rev_uplift_fy1 numeric,
    fwd_rev_uplift_fy3 numeric,
    detail          jsonb,
    prev_id         bigint,
    created_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, as_of, model_version)
);

CREATE TABLE IF NOT EXISTS forecast_actuals (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    snapshot_id     bigint REFERENCES growth_forecast_snapshots(id),
    metric          text NOT NULL,
    horizon_days    int NOT NULL,
    forecast        numeric,
    actual          numeric,
    error           numeric,
    graded_at       timestamptz DEFAULT now(),
    UNIQUE (snapshot_id, metric, horizon_days)
);

CREATE TABLE IF NOT EXISTS fundamentals_change_events (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol TEXT NOT NULL,
    as_of_date DATE NOT NULL,
    event_type TEXT NOT NULL,
    event_key TEXT NOT NULL,
    headline TEXT NOT NULL,
    severity TEXT NOT NULL,
    direction TEXT NOT NULL,
    evidence JSONB,
    recommended_action TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS macro_series_points (
    series_id        text        NOT NULL,
    observation_date date        NOT NULL,
    value            numeric,
    source           text        DEFAULT 'fred',
    retrieved_at     timestamptz DEFAULT now(),
    PRIMARY KEY (series_id, observation_date)
);

CREATE TABLE IF NOT EXISTS portfolio_agent_trade_theses (
    thesis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id TEXT,
    symbol VARCHAR(32) NOT NULL,
    setup_type VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    version INTEGER NOT NULL DEFAULT 1,
    technical_score NUMERIC(8,4),
    fundamental_score NUMERIC(8,4),
    valuation_score NUMERIC(8,4),
    catalyst_score NUMERIC(8,4),
    market_environment_score NUMERIC(8,4),
    bull_case TEXT,
    base_case TEXT,
    bear_case TEXT,
    invalidation_conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(128) NOT NULL DEFAULT 'deterministic'
);

CREATE TABLE IF NOT EXISTS portfolio_agent_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id TEXT,
    symbol VARCHAR(32) NOT NULL,
    thesis_id UUID REFERENCES portfolio_agent_trade_theses(thesis_id) ON DELETE SET NULL,
    action VARCHAR(32) NOT NULL,
    decision_confidence NUMERIC(8,6) NOT NULL,
    regime_confidence NUMERIC(8,6),
    outcome_probability NUMERIC(8,6),
    market_regime VARCHAR(128),
    strategy_environment VARCHAR(64),
    setup_type VARCHAR(64),
    risk_status VARCHAR(64),
    risk_allowed BOOLEAN,
    entry_price NUMERIC(20,8),
    stop_price NUMERIC(20,8),
    target_price NUMERIC(20,8),
    reward_risk NUMERIC(12,6),
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    vetoes JSONB NOT NULL DEFAULT '[]'::jsonb,
    rules_version VARCHAR(128) NOT NULL,
    model_version VARCHAR(128),
    prompt_version VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS portfolio_agent_allocations (
    allocation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES portfolio_agent_decisions(decision_id) ON DELETE CASCADE,
    symbol VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    allowed BOOLEAN NOT NULL DEFAULT FALSE,
    requested_value NUMERIC(20,8) NOT NULL DEFAULT 0,
    allocated_value NUMERIC(20,8) NOT NULL DEFAULT 0,
    requested_shares NUMERIC(20,8),
    allocated_shares NUMERIC(20,8) NOT NULL DEFAULT 0,
    allocation_pct NUMERIC(12,8) NOT NULL DEFAULT 0,
    risk_budget NUMERIC(20,8) NOT NULL DEFAULT 0,
    remaining_heat NUMERIC(12,8) NOT NULL DEFAULT 0,
    portfolio_exposure JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    blocking_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    rules_version VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_agent_order_plans (
    plan_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES portfolio_agent_decisions(decision_id) ON DELETE RESTRICT,
    allocation_id UUID REFERENCES portfolio_agent_allocations(allocation_id) ON DELETE SET NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(16) NOT NULL,
    order_type VARCHAR(32) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    limit_price NUMERIC(20,8),
    stop_price NUMERIC(20,8),
    target_price NUMERIC(20,8),
    time_in_force VARCHAR(16) NOT NULL DEFAULT 'DAY',
    max_slippage_bps NUMERIC(12,4) NOT NULL DEFAULT 25,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING_APPROVAL',
    approval_required BOOLEAN NOT NULL DEFAULT TRUE,
    approved_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_agent_orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES portfolio_agent_order_plans(plan_id) ON DELETE RESTRICT,
    broker_order_id TEXT,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(16) NOT NULL,
    order_type VARCHAR(32) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'NEW',
    submitted_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    expired_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    reason TEXT,
    source VARCHAR(64) NOT NULL DEFAULT 'paper',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_agent_fills (
    fill_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES portfolio_agent_orders(order_id) ON DELETE RESTRICT,
    broker_fill_id TEXT,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(16) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    price NUMERIC(20,8) NOT NULL,
    fees NUMERIC(20,8) NOT NULL DEFAULT 0,
    slippage NUMERIC(20,8),
    filled_at TIMESTAMPTZ NOT NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'paper',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_agent_position_events (
    position_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id TEXT,
    symbol VARCHAR(32) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    quantity NUMERIC(20,8),
    price NUMERIC(20,8),
    decision_id UUID REFERENCES portfolio_agent_decisions(decision_id) ON DELETE SET NULL,
    plan_id UUID REFERENCES portfolio_agent_order_plans(plan_id) ON DELETE SET NULL,
    order_id UUID REFERENCES portfolio_agent_orders(order_id) ON DELETE SET NULL,
    fill_id UUID REFERENCES portfolio_agent_fills(fill_id) ON DELETE SET NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_agent_outcomes (
    outcome_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID REFERENCES portfolio_agent_decisions(decision_id) ON DELETE SET NULL,
    thesis_id UUID REFERENCES portfolio_agent_trade_theses(thesis_id) ON DELETE SET NULL,
    symbol VARCHAR(32) NOT NULL,
    horizon VARCHAR(32) NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    return_pct NUMERIC(12,8),
    pnl NUMERIC(20,8),
    maximum_favorable_excursion NUMERIC(12,8),
    maximum_adverse_excursion NUMERIC(12,8),
    stop_hit BOOLEAN,
    target_hit BOOLEAN,
    holding_period_days INTEGER,
    fees NUMERIC(20,8),
    slippage NUMERIC(20,8),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_initiatives (
    id              bigserial PRIMARY KEY,
    symbol          text NOT NULL,
    name            text NOT NULL,
    channel         text,
    segment         text,
    stage           text NOT NULL,
    addressable_band text,
    scenario_buckets jsonb,
    incr_margin     numeric,
    confidence      numeric,
    evidence        jsonb,
    status          text DEFAULT 'active',
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    UNIQUE (symbol, name)
);

CREATE TABLE IF NOT EXISTS recovery_deployments (
    id          bigserial    PRIMARY KEY,
    as_of       date         NOT NULL DEFAULT CURRENT_DATE,
    stage       integer      NOT NULL,

    symbol      text         NOT NULL,
    alloc_usd   numeric      NOT NULL,
    note        text,
    created_at  timestamptz  DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sector_candidate_runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ran_at        timestamptz NOT NULL DEFAULT now(),
    scored        integer,
    results       jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS theme_rotation_runs (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    theme_key       text NOT NULL,
    as_of           date NOT NULL,
    rank            int,
    score           double precision,
    call            text,
    stage           text,
    rs20            double precision,
    rs60            double precision,
    rs_slope        double precision,
    breadth         double precision,
    news_hits       int,
    channel_evidence int,
    median_rev_growth double precision,
    median_revision double precision,
    covered         int,
    member_count    int,
    model_version   text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (theme_key, as_of)
);

CREATE TABLE IF NOT EXISTS wheel_positions (
    id          bigserial PRIMARY KEY,
    symbol      text NOT NULL,
    kind        text NOT NULL CHECK (kind IN ('csp', 'cc')),
    strike      numeric NOT NULL,
    expiry      date NOT NULL,
    contracts   int NOT NULL DEFAULT 1,
    premium     numeric,
    status      text NOT NULL DEFAULT 'open'
                CHECK (status IN ('open', 'assigned', 'called', 'closed', 'expired')),
    notes       text,
    opened_at   timestamptz DEFAULT now(),
    closed_at   timestamptz,
    updated_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS signal_changes (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    old_signal JSONB NOT NULL,
    new_signal JSONB NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    change_details JSONB NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CHECK (change_type IN ('SIGNAL_TYPE_CHANGE', 'CONFIDENCE_THRESHOLD_CHANGE', 'RISK_LEVEL_CHANGE', 'QUALITY_CHANGE'))
);

CREATE TABLE IF NOT EXISTS rating_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    subscription_type VARCHAR(50) NOT NULL CHECK (subscription_type IN ('rating_updates', 'price_target_updates', 'earnings_updates')),
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 2 CHECK (priority BETWEEN 1 AND 5),
    config JSONB DEFAULT '{}',
    last_processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, symbol, subscription_type)
);

CREATE TABLE IF NOT EXISTS alert_audit_trail (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('alert', 'event', 'notification', 'job', 'plugin', 'user', 'system')),
    entity_id VARCHAR(50) NOT NULL,
    entity_name VARCHAR(200),

    operation_type VARCHAR(20) NOT NULL CHECK (operation_type IN ('create', 'update', 'delete', 'trigger', 'send', 'process', 'execute', 'configure')),
    operation_data JSONB NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    state_diff JSONB,

    user_id UUID REFERENCES users(id),
    job_id VARCHAR(50),
    plugin_name VARCHAR(50),
    correlation_id VARCHAR(50),
    session_id VARCHAR(50),

    status VARCHAR(20) NOT NULL CHECK (status IN ('started', 'completed', 'failed', 'cancelled', 'timeout')),
    result_data JSONB,
    error_message TEXT,
    error_stack TEXT,
    error_code VARCHAR(50),

    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    cpu_time_ms INTEGER,
    memory_usage_mb INTEGER,

    ip_address INET,
    user_agent TEXT,
    hostname VARCHAR(100),
    process_id INTEGER,
    thread_id VARCHAR(50),

    business_context JSONB DEFAULT '{}',
    impact_level VARCHAR(20) DEFAULT 'low' CHECK (impact_level IN ('low', 'medium', 'high', 'critical')),

    tags TEXT[],
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (cpu_time_ms IS NULL OR cpu_time_ms >= 0),
    CHECK (memory_usage_mb IS NULL OR memory_usage_mb >= 0),
    CHECK (version >= 1)
);

CREATE TABLE IF NOT EXISTS analysis_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    portfolio_id UUID REFERENCES portfolios(id) ON DELETE SET NULL,

    analysis_type VARCHAR(20) NOT NULL CHECK (analysis_type IN ('single', 'portfolio', 'backtest')),
    symbols_analyzed INTEGER DEFAULT 0,
    signals_generated INTEGER DEFAULT 0,
    success_rate DECIMAL(5,2),

    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_ms INTEGER,

    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    error_message TEXT,

    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS grade_changes (
    change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(10) NOT NULL REFERENCES stocks(symbol) ON DELETE CASCADE,
    grading_company VARCHAR(100) NOT NULL,
    change_date TIMESTAMPTZ NOT NULL,
    change_type VARCHAR(20) NOT NULL CHECK (change_type IN ('upgrade', 'downgrade', 'initiate', 'suspend', 'maintain')),

    previous_grade VARCHAR(20),
    new_grade VARCHAR(20) NOT NULL,
    grade_difference INTEGER,

    price_at_change DECIMAL(10,2),
    price_change_percent DECIMAL(5,2),
    volume_at_change BIGINT,
    volume_ratio DECIMAL(5,2),

    consensus_before DECIMAL(4,2),
    consensus_after DECIMAL(4,2),
    consensus_change DECIMAL(4,2),
    analyst_count_before INTEGER,
    analyst_count_after INTEGER,

    data_source VARCHAR(50) DEFAULT 'unknown',
    source_id VARCHAR(100),
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(symbol, grading_company, change_date, data_source),
    CHECK (grade_difference IS NULL OR grade_difference != 0)
);

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
