-- Volume-confirmation columns for rotation_events (added after 092
-- already applied — schema_migrations tracks files by name, so
-- post-run edits to 092 never re-execute; this file does).
ALTER TABLE rotation_events
    ADD COLUMN IF NOT EXISTS to_money5 double precision,
    ADD COLUMN IF NOT EXISTS to_vol_ratio double precision,
    ADD COLUMN IF NOT EXISTS vol_confirmed boolean;
