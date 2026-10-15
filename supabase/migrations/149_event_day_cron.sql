-- Event-day judge: guarantee the pre-registered call journals itself.
-- snapshot() now refuses to journal before 07:00 ET (an overnight call
-- freezes premarket_spy near zero and wastes the market's first vote),
-- so lazy page-fetch journaling alone could fire post-gate or post-print.
-- 12:15 UTC = 08:15 EDT / 07:15 EST — past the gate year-round and still
-- ahead of the typical 08:30 ET release. No-ops on non-event days.
insert into job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
values ('event-day', 'Macro event judge',
        'Journal the bounded green/red/choppy pre-release call on scheduled macro days; graded vs realized SPY/QQQ close',
        'job', '15 12 * * *', true, null, 20)
on conflict (name) do update set cron=excluded.cron, purpose=excluded.purpose,
       priority=excluded.priority;
