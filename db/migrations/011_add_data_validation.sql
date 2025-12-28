-- Migration 011: Add data validation reporting table
-- Stores validation reports for data quality tracking

CREATE TABLE IF NOT EXISTS data_validation_reports (
    report_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    data_type TEXT NOT NULL,
    validation_timestamp TIMESTAMP NOT NULL,
    report_json TEXT NOT NULL,  -- JSON serialized ValidationReport
    overall_status TEXT NOT NULL CHECK(overall_status IN ('pass', 'warning', 'fail')),
    critical_issues INTEGER DEFAULT 0,
    warnings INTEGER DEFAULT 0,
    rows_dropped INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_validation_symbol_type ON data_validation_reports(symbol, data_type);
CREATE INDEX IF NOT EXISTS idx_validation_timestamp ON data_validation_reports(validation_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_validation_status ON data_validation_reports(overall_status);

