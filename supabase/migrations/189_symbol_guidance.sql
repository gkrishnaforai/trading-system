-- guidance intelligence journal — normalized guidance claims +
-- outlook/quality scores, refreshed nightly per book symbol
CREATE TABLE IF NOT EXISTS symbol_guidance (
  symbol TEXT NOT NULL, as_of DATE NOT NULL,
  outlook INT, quality INT, payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, as_of));
CREATE INDEX IF NOT EXISTS sg_asof ON symbol_guidance (as_of DESC);
