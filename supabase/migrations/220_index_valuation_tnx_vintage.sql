-- 220 — journal the 10Y yield's own vintage. The EY side uses
-- same-day estimates + prices; TNX comes from the latest
-- macro_market_data row, which can lag on weekends/holidays. Without
-- tnx_as_of the spread can silently mix vintages.

ALTER TABLE index_valuation_daily
    ADD COLUMN IF NOT EXISTS tnx_as_of DATE;
