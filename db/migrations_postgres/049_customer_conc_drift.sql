-- 049_customer_conc_drift.sql — converge symbol_customer_conc to the
-- 037 spec. Prod threw 'column "top5_note" does not exist' from
-- expectation_gap: the table exists there but predates the 037
-- CREATE (which IF NOT EXISTS then skipped). ALTER-only, fully
-- idempotent — converges whatever column subset prod has.
SELECT pg_advisory_xact_lock(715049);

CREATE TABLE IF NOT EXISTS symbol_customer_conc (
    symbol       varchar(10) PRIMARY KEY REFERENCES stocks(symbol),
    top1_pct     double precision,
    top5_note    text,
    source       text NOT NULL DEFAULT 'manual',
    as_of        date,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE symbol_customer_conc
    ADD COLUMN IF NOT EXISTS top1_pct   double precision,
    ADD COLUMN IF NOT EXISTS top5_note  text,
    ADD COLUMN IF NOT EXISTS source     text NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS as_of      date,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
