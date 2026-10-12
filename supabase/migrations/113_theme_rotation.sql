-- 113_theme_rotation.sql — per-theme rotation board journal.
-- Append-only snapshots of the deterministic theme composite
-- (member tape RS/breadth + evidence + fundamentals). The weekly diff
-- between snapshots is the "chips → memory → data-center" transition
-- record.

CREATE TABLE IF NOT EXISTS theme_rotation_runs (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    theme_key       text NOT NULL,
    as_of           date NOT NULL,
    rank            int,
    score           double precision,
    call            text,
    stage           text,
    rs20            double precision,
    rs60            double precision,
    rs_slope        double precision,
    breadth         double precision,
    news_hits       int,
    channel_evidence int,
    median_rev_growth double precision,
    median_revision double precision,
    covered         int,
    member_count    int,
    model_version   text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (theme_key, as_of)
);

CREATE INDEX IF NOT EXISTS theme_rotation_runs_asof
    ON theme_rotation_runs (as_of DESC);

INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES
  ('theme-rotation', 'Theme rotation board',
   'Score every active theme on member tape + evidence + fundamentals, '
   'journals weekly so rotations are visible as transitions',
   '40 22 * * 1-5', true, '{momentum,tailwinds}', 30, 5, 40)
ON CONFLICT (name) DO NOTHING;
