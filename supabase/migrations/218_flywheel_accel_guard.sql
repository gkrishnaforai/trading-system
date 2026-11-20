-- accel guard flags + pctile sample depth — a stored accel of 0.0 is
-- deliberately clamped (normalization off triple-digit base, or a
-- ~zero-base diff) but reads identically to a measured zero. The flag
-- lets the card say "normalizing" instead of "+0pts". pctile_n
-- journals the observation count so "vs history" is honest about
-- how much history exists (snapshots began 2026-09-30).

ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS rev_accel_guarded BOOLEAN,
    ADD COLUMN IF NOT EXISTS eps_accel_guarded BOOLEAN,
    ADD COLUMN IF NOT EXISTS fwd_pe_pctile_n  INT;
