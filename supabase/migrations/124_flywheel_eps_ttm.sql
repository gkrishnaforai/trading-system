-- 124: TTM-basis EPS growth for the flywheel. Single-quarter YoY EPS
-- is the noisiest fundamental leg (tax timing, SBC vesting, acquisition
-- amortization, one-offs) — NOW Q2'26 printed -21.6% quarterly YoY while
-- TTM EPS was flat (+0.6%). Level-deterioration legs in
-- fundamental_health must be judged on the smoothed basis; quarterly
-- remains as momentum detail. Double precision to match sibling columns
-- and stay JSON-serializable (see gm_qoq / migration 122).
ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS eps_growth_ttm double precision;
