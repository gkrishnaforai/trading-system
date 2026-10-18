-- R&D intensity on the flywheel — for software names the R&D ramp is
-- the buildout. rd_rev = latest-quarter R&D/revenue; rd_slope = that
-- ratio vs the year-ago quarter. Feeds decel_cause=rd_investment so
-- EPS/FCF compression from an R&D ramp reads as investment, not decay.
ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS rd_rev NUMERIC,
    ADD COLUMN IF NOT EXISTS rd_slope NUMERIC;
