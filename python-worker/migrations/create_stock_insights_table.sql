-- Create stock insights snapshots table for storing comprehensive analysis
CREATE TABLE IF NOT EXISTS stock_insights_snapshots (
  stock_symbol TEXT NOT NULL,
  insights_date DATE NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (stock_symbol, insights_date)
);

CREATE INDEX IF NOT EXISTS idx_stock_insights_symbol_date ON stock_insights_snapshots(stock_symbol, insights_date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_insights_generated_at ON stock_insights_snapshots(generated_at DESC);
