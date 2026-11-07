-- flow footprint journal — EOD institutional-signature per book symbol
CREATE TABLE IF NOT EXISTS symbol_flow (
  symbol TEXT NOT NULL,
  as_of DATE NOT NULL,
  zvol NUMERIC, clv NUMERIC, sig TEXT, event BOOLEAN,
  footprint TEXT, streak INT, payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, as_of));
CREATE INDEX IF NOT EXISTS sf_asof ON symbol_flow (as_of DESC);
