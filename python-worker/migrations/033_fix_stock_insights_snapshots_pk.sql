-- Make stock_insights_snapshots store multiple sources per day without overwriting.
-- Previous schema used PRIMARY KEY (stock_symbol, insights_date) which caused data loss across sources.

ALTER TABLE IF EXISTS stock_insights_snapshots
  DROP CONSTRAINT IF EXISTS stock_insights_snapshots_pkey;

ALTER TABLE IF EXISTS stock_insights_snapshots
  ADD CONSTRAINT stock_insights_snapshots_pkey PRIMARY KEY (stock_symbol, insights_date, source);

CREATE INDEX IF NOT EXISTS idx_stock_insights_symbol_date_source
  ON stock_insights_snapshots(stock_symbol, insights_date DESC, source);
