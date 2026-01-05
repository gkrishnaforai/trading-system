CREATE TABLE IF NOT EXISTS data_validation_reports (
  report_id TEXT PRIMARY KEY,
  symbol TEXT NOT NULL,
  data_type TEXT NOT NULL,
  validation_timestamp TIMESTAMPTZ NOT NULL,
  report_json JSONB NOT NULL,
  overall_status TEXT NOT NULL,
  critical_issues INTEGER NOT NULL DEFAULT 0,
  warnings INTEGER NOT NULL DEFAULT 0,
  rows_dropped INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_validation_reports_symbol_type_ts
  ON data_validation_reports (symbol, data_type, validation_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_data_validation_reports_ts
  ON data_validation_reports (validation_timestamp DESC);

DROP TRIGGER IF EXISTS trg_data_validation_reports_updated_at ON data_validation_reports;

CREATE TRIGGER trg_data_validation_reports_updated_at
BEFORE UPDATE ON data_validation_reports
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
