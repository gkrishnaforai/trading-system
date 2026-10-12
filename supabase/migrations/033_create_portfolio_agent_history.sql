-- Portfolio Agent canonical history and execution lineage.
-- Additive migration: does not replace legacy portfolios/holdings/signals tables.
-- IDs are text-compatible with existing Python/Go portfolio APIs.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS portfolio_agent_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    account_equity NUMERIC(20,6),
    settled_cash NUMERIC(20,6),
    unsettled_cash NUMERIC(20,6),
    buying_power NUMERIC(20,6),
    invested_value NUMERIC(20,6),
    portfolio_heat NUMERIC(12,8),
    price_freshness VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    missing_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    source VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_snapshots_portfolio_asof
    ON portfolio_agent_snapshots(portfolio_id, as_of DESC);

CREATE TABLE IF NOT EXISTS portfolio_agent_position_states (
    position_state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id UUID NOT NULL REFERENCES portfolio_agent_snapshots(snapshot_id) ON DELETE CASCADE,
    portfolio_id TEXT NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    asset_type VARCHAR(32) NOT NULL DEFAULT 'stock',
    side VARCHAR(16) NOT NULL DEFAULT 'LONG',
    quantity NUMERIC(20,8) NOT NULL DEFAULT 0,
    average_entry_price NUMERIC(20,8),
    current_price NUMERIC(20,8),
    current_value NUMERIC(20,8),
    unrealized_pnl NUMERIC(20,8),
    unrealized_pnl_pct NUMERIC(12,8),
    sector VARCHAR(128),
    industry VARCHAR(128),
    stop_price NUMERIC(20,8),
    target_price NUMERIC(20,8),
    thesis_id UUID,
    decision_id UUID,
    opened_at TIMESTAMPTZ,
    as_of TIMESTAMPTZ NOT NULL,
    price_as_of TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    source VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_positions_snapshot
    ON portfolio_agent_position_states(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_agent_positions_symbol_asof
    ON portfolio_agent_position_states(symbol, as_of DESC);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_theses_symbol_status
    ON portfolio_agent_trade_theses(symbol, status, updated_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_decisions_portfolio_created
    ON portfolio_agent_decisions(portfolio_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_agent_decisions_symbol_created
    ON portfolio_agent_decisions(symbol, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_allocations_decision
    ON portfolio_agent_allocations(decision_id);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_order_plans_status_created
    ON portfolio_agent_order_plans(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_agent_order_plans_symbol
    ON portfolio_agent_order_plans(symbol, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_orders_plan
    ON portfolio_agent_orders(plan_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_agent_orders_symbol_status
    ON portfolio_agent_orders(symbol, status, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_fills_order
    ON portfolio_agent_fills(order_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_agent_fills_symbol_time
    ON portfolio_agent_fills(symbol, filled_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_position_events_symbol_time
    ON portfolio_agent_position_events(symbol, occurred_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_portfolio_agent_outcomes_symbol_horizon
    ON portfolio_agent_outcomes(symbol, horizon, as_of DESC);
