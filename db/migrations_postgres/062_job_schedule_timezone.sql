ALTER TABLE job_definitions
  ADD COLUMN IF NOT EXISTS timezone text NOT NULL DEFAULT 'UTC';

INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, timezone)
VALUES ('morning-regime', 'Morning regime engine',
        'Daily 7-bucket deterministic score → 5-regime class → LLM explanation',
        'job', '0 8 * * 1-5', true, 'America/New_York')
ON CONFLICT (name) DO UPDATE SET
  cron = '0 8 * * 1-5',
  enabled = true,
  timezone = 'America/New_York',
  updated_at = now();
