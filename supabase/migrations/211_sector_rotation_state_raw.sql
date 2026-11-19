-- sector_rotation_daily: journal the ungated state alongside the
-- persistence-gated one. The replay showed 'probable' is right when
-- deterioration persists but wrong on one-day washouts — the gate
-- (MIN_PERSIST=2) emits `state`, while `state_raw` keeps what the
-- legs actually scored so the gate itself can be graded/tuned.
ALTER TABLE sector_rotation_daily
    ADD COLUMN IF NOT EXISTS state_raw TEXT;
