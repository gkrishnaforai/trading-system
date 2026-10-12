-- Price-target watch — daily snapshot of FMP's analyst PT summary per
-- symbol. Upgrades surface as PT repricing before/alongside headlines:
-- lastMonthAvgPriceTarget jumping vs the quarter average + fresh PT count
-- is the "analysts are re-rating this name" signal. Works even when the
-- grades feed is unavailable (FMP grades/ratings are 404 on this plan).

CREATE TABLE IF NOT EXISTS pt_snapshots (
    id           bigserial PRIMARY KEY,
    symbol       text NOT NULL,
    as_of        date NOT NULL DEFAULT current_date,
    month_avg    numeric,
    month_count  int,
    quarter_avg  numeric,
    quarter_count int,
    year_avg     numeric,
    year_count   int,
    consensus    numeric,
    median       numeric,
    high         numeric,
    low          numeric,
    price        numeric,
    created_at   timestamptz DEFAULT now(),
    UNIQUE (symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_pt_snap_date ON pt_snapshots (as_of);
