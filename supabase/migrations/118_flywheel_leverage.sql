-- Leverage leg for the flywheel — the balance-sheet factor the TLN
-- comparison exposed as missing (their "Balance Sheet 67" vs our
-- blind spot). Sourced from FMP key-metrics-ttm inside the existing
-- per-symbol flywheel refresh (no new fetch path).

ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS net_debt_ebitda double precision,
    ADD COLUMN IF NOT EXISTS debt_to_equity   double precision;
