-- Margin-quality + EPS-basis fields on the flywheel.
-- om_*: operating margin — GM-vs-OM split discriminates product
-- economics decay from opex/acquisition burden. sbc_rev: equity comp
-- as % of revenue (deal retention grants inflate GAAP losses).
-- eps_rep / eps_rep_growth: reported (non-GAAP headline) EPS series —
-- the gap vs GAAP growth IS the accounting-effect detector.
ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS om_now NUMERIC,
    ADD COLUMN IF NOT EXISTS om_qoq NUMERIC,
    ADD COLUMN IF NOT EXISTS om_slope NUMERIC,
    ADD COLUMN IF NOT EXISTS sbc_rev NUMERIC,
    ADD COLUMN IF NOT EXISTS eps_rep NUMERIC,
    ADD COLUMN IF NOT EXISTS eps_rep_growth NUMERIC;
