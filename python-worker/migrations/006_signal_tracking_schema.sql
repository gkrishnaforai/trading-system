-- Signal History Tracking Schema
-- Industry-standard signal persistence and change detection

-- Signal History Table
CREATE TABLE IF NOT EXISTS signal_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    analysis_date DATE NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    signal_data JSONB NOT NULL,
    engine_version VARCHAR(20) DEFAULT '1.0',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    UNIQUE(symbol, analysis_date, timestamp)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_signal_history_symbol_date ON signal_history(symbol, analysis_date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_history_timestamp ON signal_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_history_symbol ON signal_history(symbol);

-- Signal Changes Table (for alerts)
CREATE TABLE IF NOT EXISTS signal_changes (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    old_signal JSONB NOT NULL,
    new_signal JSONB NOT NULL,
    change_type VARCHAR(50) NOT NULL,
    change_details JSONB NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CHECK (change_type IN ('SIGNAL_TYPE_CHANGE', 'CONFIDENCE_THRESHOLD_CHANGE', 'RISK_LEVEL_CHANGE', 'QUALITY_CHANGE'))
);

-- Indexes for change tracking
CREATE INDEX IF NOT EXISTS idx_signal_changes_symbol_time ON signal_changes(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_changes_type ON signal_changes(change_type);
CREATE INDEX IF NOT EXISTS idx_signal_changes_timestamp ON signal_changes(timestamp DESC);

-- Signal Performance Tracking (optional for future enhancement)
CREATE TABLE IF NOT EXISTS signal_performance (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    signal_date DATE NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    signal_confidence FLOAT NOT NULL,
    entry_price FLOAT NOT NULL,
    exit_price FLOAT,
    exit_date DATE,
    holding_days INTEGER,
    return_percent FLOAT,
    max_drawdown FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CHECK (signal_type IN ('BUY', 'SELL', 'HOLD', 'AVOID', 'MONITORING')),
    CHECK (signal_confidence >= 0 AND signal_confidence <= 1)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_signal_performance_symbol_date ON signal_performance(symbol, signal_date DESC);
CREATE INDEX IF NOT EXISTS idx_signal_performance_return ON signal_performance(return_percent DESC);
CREATE INDEX IF NOT EXISTS idx_signal_performance_type ON signal_performance(signal_type);

-- Alert Rules Table (for configurable alert thresholds)
CREATE TABLE IF NOT EXISTS alert_rules (
    id SERIAL PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL UNIQUE,
    rule_type VARCHAR(50) NOT NULL,
    conditions JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CHECK (rule_type IN ('SIGNAL_TYPE_CHANGE', 'CONFIDENCE_THRESHOLD', 'RISK_LEVEL_CHANGE', 'VOLUME_SPIKE', 'VOLATILITY_EXPANSION'))
);

-- Alert History Table
CREATE TABLE IF NOT EXISTS alert_history (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,
    alert_message TEXT NOT NULL,
    alert_data JSONB NOT NULL,
    triggered_at TIMESTAMP NOT NULL,
    acknowledged_at TIMESTAMP,
    is_acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CHECK (alert_type IN ('SIGNAL_TYPE_CHANGE', 'CONFIDENCE_THRESHOLD', 'RISK_LEVEL_CHANGE', 'VOLUME_SPIKE', 'VOLATILITY_EXPANSION', 'RECOVERY_SIGNAL'))
);

-- Alert indexes
CREATE INDEX IF NOT EXISTS idx_alert_history_symbol_time ON alert_history(symbol, triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_history_type ON alert_history(alert_type);
CREATE INDEX IF NOT EXISTS idx_alert_history_acknowledged ON alert_history(is_acknowledged);

-- Comments for documentation
COMMENT ON TABLE signal_history IS 'Historical signal data for tracking and analysis';
COMMENT ON TABLE signal_changes IS 'Signal change events for alert generation';
COMMENT ON TABLE signal_performance IS 'Signal performance tracking for strategy optimization';
COMMENT ON TABLE alert_rules IS 'Configurable alert rules and thresholds';
COMMENT ON TABLE alert_history IS 'Historical alert events and acknowledgments';

-- Sample alert rules (can be inserted via application)
INSERT INTO alert_rules (rule_name, rule_type, conditions) VALUES
('High Confidence Recovery', 'CONFIDENCE_THRESHOLD', '{"min_confidence": 0.65, "signal_types": ["RECOVERY_ENTRY"]}'),
('Signal Type Change Alert', 'SIGNAL_TYPE_CHANGE', '{"track_all_symbols": true, "importance_threshold": "MEDIUM"}'),
('Risk Level Escalation', 'RISK_LEVEL_CHANGE', '{"alert_on_increase": true, "min_risk_level": "HIGH"}')
ON CONFLICT (rule_name) DO NOTHING;
