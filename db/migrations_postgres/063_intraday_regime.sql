CREATE TABLE IF NOT EXISTS regime_intraday_snapshots (
    id              bigserial PRIMARY KEY,
    as_of           timestamptz NOT NULL UNIQUE,
    session_date    date NOT NULL,
    market_time     timestamptz NOT NULL,
    baseline_as_of  date,
    baseline_regime text,
    baseline_score  double precision,
    tape_state      text,
    tape_ts         timestamptz,
    state           text NOT NULL,
    action          text NOT NULL,
    tone            text NOT NULL,
    evidence        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_regime_intraday_session
    ON regime_intraday_snapshots (session_date, as_of DESC);

INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, timezone, depends_on, dep_max_age_h, priority, cooldown_min)
VALUES ('intraday-regime', 'Intraday regime overlay',
        'Hourly timestamped regime update — daily baseline × intraday tape, advisory timing only',
        'job', '0 8-17 * * 1-5', true, 'America/New_York', '{morning-regime}', 12, 65, 15)
ON CONFLICT (name) DO UPDATE SET
  label = EXCLUDED.label, purpose = EXCLUDED.purpose,
  cron = EXCLUDED.cron, enabled = true,
  timezone = EXCLUDED.timezone, depends_on = EXCLUDED.depends_on,
  dep_max_age_h = EXCLUDED.dep_max_age_h,
  priority = EXCLUDED.priority, cooldown_min = EXCLUDED.cooldown_min,
  updated_at = now();
