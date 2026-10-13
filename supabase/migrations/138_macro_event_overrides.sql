-- Provider-verified macro release dates
-- Baseline event dates in code are hardcoded BLS/Fed schedules
-- Bureau reschedules are real (Sept-2025 CPI slid Oct 15 to Oct 24)
-- econ-cal-verify job reconciles against Finnhub daily and lands here

CREATE TABLE IF NOT EXISTS macro_event_overrides (
    kind            text        NOT NULL,
    event_date      date        NOT NULL,
    name            text        NOT NULL,
    original_date   date,
    status          text        NOT NULL DEFAULT 'confirmed',
    source          text        NOT NULL DEFAULT 'finnhub',
    time_et         text,
    severity        text,
    verified_at     timestamptz DEFAULT now(),
    PRIMARY KEY (kind, event_date)
);

CREATE INDEX IF NOT EXISTS idx_macro_event_overrides_date
    ON macro_event_overrides (event_date);

-- verify daily 8:05 ET (12:05 UTC) before morning-regime builds the card
insert into job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
values ('econ-cal-verify', 'Macro calendar verification',
        'Fetch Finnhub economic calendar, reconcile against hardcoded release dates, store corrected dates',
        'job', '5 12 * * *', true, null, 13)
on conflict (name) do update set cron=excluded.cron, purpose=excluded.purpose,
       priority=excluded.priority;
