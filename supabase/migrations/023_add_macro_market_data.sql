CREATE TABLE IF NOT EXISTS macro_market_data (
  data_date date PRIMARY KEY,

  vix_close numeric,

  nasdaq_symbol text,
  nasdaq_close numeric,
  nasdaq_sma50 numeric,
  nasdaq_sma200 numeric,

  tnx_yield numeric,
  irx_yield numeric,
  yield_curve_spread numeric,

  sp500_above_50d_pct numeric,

  source text,
  updated_at timestamptz NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_macro_market_data_updated_at ON macro_market_data;

CREATE TRIGGER trg_macro_market_data_updated_at
BEFORE UPDATE ON macro_market_data
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_macro_market_data_date_desc
  ON macro_market_data (data_date DESC);
