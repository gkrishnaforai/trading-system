-- 232_customer_conc_history.sql — drift needs history.
--
-- symbol_customer_conc holds the LATEST curated top-1 customer share
-- (manual source — XBRL has no customer-share tag). The reviewer's
-- ask is 'becoming more dependent?' = drift over time. Every read
-- via customer_conc() journals an observation here when the level
-- changes or ≥30d pass; drift = latest vs prior observation.

SELECT pg_advisory_xact_lock(715232);

CREATE TABLE IF NOT EXISTS symbol_customer_conc_hist (
    id         BIGSERIAL PRIMARY KEY,
    symbol     TEXT NOT NULL,
    as_of      DATE NOT NULL,
    top1_pct   DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of)
);
CREATE INDEX IF NOT EXISTS cust_conc_hist_sym
    ON symbol_customer_conc_hist (symbol, as_of DESC);
