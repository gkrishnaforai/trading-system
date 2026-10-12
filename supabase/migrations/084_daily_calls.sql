-- Daily calls — the board's distilled top-3 swing picks per session.
-- Journaled so the outcome engine can grade OUR calls, not just setups.
CREATE TABLE IF NOT EXISTS daily_calls (
    id          bigserial PRIMARY KEY,
    call_date   date        NOT NULL,
    rank        int         NOT NULL,
    symbol      text        NOT NULL,
    score       double precision,
    entry_px    double precision,
    stop_px     double precision,
    target_px   double precision,
    rr          double precision,
    state       text,
    dip_phase   text,
    evidence    jsonb       DEFAULT '[]',
    created_at  timestamptz DEFAULT now(),
    UNIQUE (call_date, symbol)
);
CREATE INDEX IF NOT EXISTS daily_calls_date_idx ON daily_calls (call_date DESC);

-- scheduler seeds for the two new jobs
INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES
  ('daily-calls', 'Top-3 swing calls',
   'Distill the scored board into 3 actionable calls with plans',
   '30 23 * * 1-5', true, '{momentum,fund-flags}', 24, 15, 75),
  ('meta', 'Signal self-training',
   'Nightly signal-lift ablation + calibration → engine_weights',
   '45 23 * * 1-5', true, '{pilot}', 26, 30, 85)
ON CONFLICT (name) DO UPDATE SET cron=EXCLUDED.cron,
    enabled=EXCLUDED.enabled, depends_on=EXCLUDED.depends_on,
    priority=EXCLUDED.priority;
