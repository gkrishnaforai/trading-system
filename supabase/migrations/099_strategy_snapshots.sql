-- Portfolio strategy journal — the top-down allocation layer.
-- One row per day: regime → rotation → events → earnings → theme
-- scores → target weights. Versioned so "was the allocation read
-- right" is a gradeable question over time, not commentary.
CREATE TABLE IF NOT EXISTS strategy_snapshots (
    id              bigserial PRIMARY KEY,
    snap_date       date NOT NULL UNIQUE,
    engine_version  text NOT NULL,
    payload         jsonb NOT NULL,   -- {morning, rotation, events,
                                    --   earnings, themes, current,
                                    --   weights}
    -- graded later: did the top-scored theme actually outperform?
    top_theme       text,
    top_theme_ret_20d double precision,
    spy_ret_20d     double precision,
    graded_at       timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS strategy_snapshots_date_idx
    ON strategy_snapshots (snap_date DESC);
