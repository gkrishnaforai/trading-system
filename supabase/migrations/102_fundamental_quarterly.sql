-- Fundamental quarterly journal — point-in-time financials for the
-- Hidden Gems scanner + backtest. FMP returns `filingDate` per row,
-- which is the look-ahead-safe availability timestamp: a factor may
-- only use quarters whose filing_date <= the evaluation date.
-- Wide row keyed (symbol, period_end) merges income + balance-sheet
-- + cash-flow statements.
CREATE TABLE IF NOT EXISTS fundamental_quarterly (
    id            bigserial PRIMARY KEY,
    symbol        text NOT NULL,
    period_end    date NOT NULL,
    filing_date   date,              -- when the market learned it
    -- income statement
    revenue            double precision,
    gross_profit       double precision,
    operating_income   double precision,
    net_income         double precision,
    eps_diluted        double precision,
    shares_diluted     double precision,   -- dilution tracking
    -- balance sheet
    total_assets       double precision,
    total_liabilities  double precision,
    equity             double precision,   -- ROE denominator
    total_debt         double precision,
    cash               double precision,
    -- cash flow
    operating_cf       double precision,
    capex              double precision,
    free_cf            double precision,
    as_of              timestamptz NOT NULL DEFAULT now(),  -- journaled
    UNIQUE (symbol, period_end)
);
CREATE INDEX IF NOT EXISTS fq_sym_idx
    ON fundamental_quarterly (symbol, period_end DESC);
CREATE INDEX IF NOT EXISTS fq_filing_idx
    ON fundamental_quarterly (filing_date);
