-- 221 — earnings-health leg on the daily market journal. A thin
-- valuation cushion with rising revisions is a different regime than
-- a thin cushion with cuts; this is the second score.
--
-- eps_rev_*   : 30d revision breadth over the tracked universe,
--               same-fiscal-year-vintage comparisons only
-- fwd_eps_*   : cap-weighted FY1→FY2 EPS growth proxy
-- earnings_*  : deterministic verdict tier + dual-register text

ALTER TABLE index_valuation_daily
    ADD COLUMN IF NOT EXISTS eps_rev_n INTEGER,
    ADD COLUMN IF NOT EXISTS eps_rev_up_n INTEGER,
    ADD COLUMN IF NOT EXISTS eps_rev_down_n INTEGER,
    ADD COLUMN IF NOT EXISTS eps_rev_flat_n INTEGER,
    ADD COLUMN IF NOT EXISTS eps_rev_breadth NUMERIC,
    ADD COLUMN IF NOT EXISTS fwd_eps_growth_fy1_fy2 NUMERIC,
    ADD COLUMN IF NOT EXISTS fwd_eps_growth_n INTEGER,
    ADD COLUMN IF NOT EXISTS earnings_verdict TEXT,
    ADD COLUMN IF NOT EXISTS earnings_tone TEXT,
    ADD COLUMN IF NOT EXISTS earnings_headline TEXT,
    ADD COLUMN IF NOT EXISTS earnings_detail TEXT;
