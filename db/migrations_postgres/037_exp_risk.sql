-- 037_exp_risk.sql (db-tree mirror of supabase 153) — Growth Expectations Risk layer.
--
-- symbol_flywheel gains the expectations-vs-price metrics the risk
-- axis needs. The warning we are building is the divergence: price
-- rising while forward estimates stop improving means returns are
-- coming from multiple expansion — fragile to the first cut.
--
--   mult_expansion_pct   P/E expansion share of the ~90d price move:
--                        (1+dP)/(1+dE)-1 where dE is the fwd-EPS
--                        revision over the same window. >0 means the
--                        rally outran the estimate.
--   fwd_pe_pctile        fwd P/E vs its OWN history (the journaled
--                        fundamental_snapshots series) — 'expectations
--                        too demanding' measured relative to the
--                        stock's own tape, not an absolute threshold.
--   h2_growth_load       share of the in-progress FY's expected EPS
--                        growth still unreported — the back-half-load
--                        check. >1.0 means the year's modeled growth
--                        exceeds everything printed so far. Only
--                        stored once >=2 quarters have reported.
--   px_rev_divergence    price up materially over the window while the
--                        forward estimate went nowhere — the named
--                        warning state.
--   cust_top1_pct        revenue share of the top disclosed customer —
--                        manually annotated; 10-K text extraction can
--                        fill it later.
--
-- symbol_customer_conc: manual/LLM-annotated concentration. XBRL
-- has no standard customer-share tag — the data lives in 10-K text.

SELECT pg_advisory_xact_lock(715037);

ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS mult_expansion_pct double precision,
    ADD COLUMN IF NOT EXISTS fwd_pe_pctile      double precision,
    ADD COLUMN IF NOT EXISTS h2_growth_load     double precision,
    ADD COLUMN IF NOT EXISTS px_rev_divergence  boolean,
    ADD COLUMN IF NOT EXISTS cust_top1_pct      double precision,
    ADD COLUMN IF NOT EXISTS cust_note          text;

CREATE TABLE IF NOT EXISTS symbol_customer_conc (
    symbol       varchar(10) PRIMARY KEY REFERENCES stocks(symbol),
    top1_pct     double precision,      -- top customer revenue share
    top5_note    text,                  -- 'MSFT/GOOGL/AMZN/META ~60% of rev'
    source       text NOT NULL DEFAULT 'manual',  -- manual | 10k_extract
    as_of        date,
    updated_at   timestamptz NOT NULL DEFAULT now()
);
