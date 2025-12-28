-- Migration 012: Add data fetch audit and signal readiness tracking
-- Tracks all data fetch operations and signal readiness validation

CREATE TABLE IF NOT EXISTS data_fetch_audit (
    audit_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    fetch_type TEXT NOT NULL,  -- 'historical', 'current', 'fundamentals', 'news', 'earnings', 'industry_peers'
    fetch_mode TEXT NOT NULL,  -- 'scheduled', 'on_demand', 'periodic', 'live'
    fetch_timestamp TIMESTAMP NOT NULL,
    data_source TEXT,  -- 'yahoo_finance', 'finnhub', 'fallback', etc.
    rows_fetched INTEGER DEFAULT 0,
    rows_saved INTEGER DEFAULT 0,
    fetch_duration_ms INTEGER,  -- Duration in milliseconds
    success BOOLEAN NOT NULL,
    error_message TEXT,
    validation_report_id TEXT,  -- Reference to data_validation_reports
    metadata TEXT,  -- JSON metadata about the fetch
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (validation_report_id) REFERENCES data_validation_reports(report_id)
);

CREATE TABLE IF NOT EXISTS signal_readiness (
    readiness_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    signal_type TEXT NOT NULL,  -- 'swing_trend', 'technical', 'hybrid_llm'
    readiness_status TEXT NOT NULL CHECK(readiness_status IN ('ready', 'not_ready', 'partial')),
    required_indicators TEXT NOT NULL,  -- JSON array of required indicators
    available_indicators TEXT NOT NULL,  -- JSON array of available indicators
    missing_indicators TEXT,  -- JSON array of missing indicators
    data_quality_score REAL,  -- 0.0 to 1.0
    validation_report_id TEXT,  -- Reference to latest validation report
    readiness_timestamp TIMESTAMP NOT NULL,
    readiness_reason TEXT,  -- Why signal is ready/not ready
    recommendations TEXT,  -- JSON array of recommendations
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (validation_report_id) REFERENCES data_validation_reports(report_id)
);

CREATE INDEX IF NOT EXISTS idx_fetch_audit_symbol ON data_fetch_audit(symbol, fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_audit_type ON data_fetch_audit(fetch_type, fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_fetch_audit_success ON data_fetch_audit(success, fetch_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_readiness_symbol ON signal_readiness(symbol, readiness_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_readiness_status ON signal_readiness(readiness_status, readiness_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_readiness_type ON signal_readiness(signal_type, readiness_timestamp DESC);

