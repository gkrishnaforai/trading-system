-- Ensure fundamentals_snapshots supports upsert on (stock_symbol, as_of_date)

CREATE UNIQUE INDEX IF NOT EXISTS uq_fundamentals_snapshots_symbol_asof
ON fundamentals_snapshots(stock_symbol, as_of_date);
