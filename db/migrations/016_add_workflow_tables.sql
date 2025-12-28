-- Workflow orchestration tables for robust data pipeline
-- Industry Standard: State management, audit trail, recovery

-- Main workflow execution tracking
CREATE TABLE IF NOT EXISTS workflow_executions (
    workflow_id TEXT PRIMARY KEY,
    workflow_type TEXT NOT NULL,  -- 'daily_batch', 'on_demand', 'recovery', 'manual'
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'paused', 'cancelled')),
    current_stage TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    metadata_json TEXT,  -- JSON with progress, counts, symbols, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stage-level execution tracking
CREATE TABLE IF NOT EXISTS workflow_stage_executions (
    stage_execution_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,  -- 'ingestion', 'validation', 'indicators', 'signals', 'scoring', 'caching'
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    symbols_processed INTEGER DEFAULT 0,
    symbols_succeeded INTEGER DEFAULT 0,
    symbols_failed INTEGER DEFAULT 0,
    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id)
);

-- Symbol-level state tracking (granular progress)
CREATE TABLE IF NOT EXISTS workflow_symbol_states (
    id BIGSERIAL PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'skipped', 'retrying')),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id),
    UNIQUE(workflow_id, symbol, stage)
);

-- Workflow checkpoints for recovery
CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    state_json TEXT NOT NULL,  -- JSON with symbol list, progress, etc.
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id)
);

-- Dead Letter Queue for failed items requiring manual review
CREATE TABLE IF NOT EXISTS workflow_dlq (
    dlq_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    stage TEXT NOT NULL,
    error_message TEXT NOT NULL,
    error_type TEXT,  -- 'validation', 'computation', 'gate_failed', 'transient'
    context_json TEXT,  -- JSON with full context
    retry_count INTEGER DEFAULT 0,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    resolved_by TEXT,  -- User or system
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id)
);

-- Workflow gate results (audit trail for gate checks)
CREATE TABLE IF NOT EXISTS workflow_gate_results (
    gate_result_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    symbol TEXT NOT NULL,
    gate_name TEXT NOT NULL,  -- 'data_ingestion', 'indicator_computation', 'signal_generation'
    passed BOOLEAN NOT NULL,
    reason TEXT,
    action TEXT,  -- 'RETRY', 'FIX_DATA_QUALITY', 'SKIP', etc.
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_workflow_status ON workflow_executions(status);
CREATE INDEX IF NOT EXISTS idx_workflow_type ON workflow_executions(workflow_type);
CREATE INDEX IF NOT EXISTS idx_workflow_created ON workflow_executions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stage_workflow ON workflow_stage_executions(workflow_id, stage_name);
CREATE INDEX IF NOT EXISTS idx_stage_status ON workflow_stage_executions(status);
CREATE INDEX IF NOT EXISTS idx_symbol_workflow ON workflow_symbol_states(workflow_id, symbol);
CREATE INDEX IF NOT EXISTS idx_symbol_stage ON workflow_symbol_states(symbol, stage, status);
CREATE INDEX IF NOT EXISTS idx_checkpoint_workflow ON workflow_checkpoints(workflow_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_dlq_unresolved ON workflow_dlq(resolved, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dlq_symbol ON workflow_dlq(symbol, stage);
CREATE INDEX IF NOT EXISTS idx_gate_workflow ON workflow_gate_results(workflow_id, stage, symbol);

