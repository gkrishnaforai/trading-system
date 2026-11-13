-- Weekly calendar audit journal — the change-report layer over the
-- existing refresh jobs (econ-cal-verify 3x daily, flywheel
-- weeknights). Every Saturday the audit fingerprints the macro
-- calendar + tracked-universe earnings dates, diffs against last
-- week's snapshot, and journals what moved. scope='*_snapshot' rows
-- carry the full fingerprint for the next run's diff.

CREATE TABLE IF NOT EXISTS calendar_audit (
    id           bigserial    PRIMARY KEY,
    run_id       uuid         NOT NULL,
    as_of        date         NOT NULL,
    scope        text         NOT NULL,   -- macro | earnings |
                                          -- macro_snapshot |
                                          -- earnings_snapshot
    event_kind   text,
    symbol       text,
    change_type  text         NOT NULL,   -- added|moved|removed|
                                          -- stale_fixed|
                                          -- provider_disagreement|
                                          -- snapshot
    old_date     date,
    new_date     date,
    detail       jsonb,
    created_at   timestamptz  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_calendar_audit_run
    ON calendar_audit (run_id);
CREATE INDEX IF NOT EXISTS idx_calendar_audit_asof
    ON calendar_audit (as_of, scope);

-- Saturdays 13:00 UTC = 08:00 ET (winter) / 09:00 ET (summer) —
-- weekly look-ahead over the next ~45d of macro events plus the
-- tracked universe's earnings dates.
INSERT INTO job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
VALUES ('calendar-audit', 'Weekly calendar audit',
        'Diff the next 45d of macro events and tracked earnings dates against last week; refresh stale dates; journal every move',
        'job', '0 13 * * 6', true, null, 14)
ON CONFLICT (name) DO UPDATE SET cron=excluded.cron, purpose=excluded.purpose,
       priority=excluded.priority;
