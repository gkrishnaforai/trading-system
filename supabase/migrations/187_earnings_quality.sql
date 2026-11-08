-- forensic earnings-quality journal — accruals/DSO/inventory/FCF
-- conversion/goodwill from XBRL, nightly, book-only
CREATE TABLE IF NOT EXISTS symbol_earnings_quality (
  symbol TEXT NOT NULL,
  as_of DATE NOT NULL,
  quality INT, flags JSONB, legs JSONB, payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, as_of));
CREATE INDEX IF NOT EXISTS seq_asof ON symbol_earnings_quality (as_of DESC);
