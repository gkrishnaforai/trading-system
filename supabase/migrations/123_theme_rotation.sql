-- Daily AI-rotation environment score (signals/theme_rotation.py) —
-- permissions directional bear-alpha entries; replayable point-in-time.
CREATE TABLE IF NOT EXISTS theme_rotation_snapshots (
    as_of   date PRIMARY KEY,
    score   double precision,
    band    varchar(24),
    legs    jsonb DEFAULT '{}'::jsonb,
    missing jsonb DEFAULT '[]'::jsonb
);
