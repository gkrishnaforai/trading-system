-- 234_job_runs_run_id.sql — per-execution id minted at dispatch time,
-- journaled here and stamped on JOB_START/JOB_END/JOB_FAIL log
-- markers, so an external watchdog can correlate ledger ↔ logs.
ALTER TABLE job_runs
    ADD COLUMN IF NOT EXISTS run_id text;
CREATE INDEX IF NOT EXISTS job_runs_run_id ON job_runs(run_id);
