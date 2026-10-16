-- Event-day judge: guarantee the pre-registered call journals itself.
-- snapshot() refuses to journal before 07:00 ET so an overnight call
-- cannot freeze premarket_spy near zero. 12:15 UTC lands at 08:15 EDT
-- or 07:15 EST, past the gate year-round and ahead of the typical
-- 08:30 ET release. No-ops on non-event days.
-- NOTE: keep apostrophes out of comments and semicolons out of string
-- literals - the go-api boot splitter mis-tracks quotes inside comments.
insert into job_definitions (name, label, purpose, kind, cron, enabled, depends_on, priority)
values ('event-day', 'Macro event judge',
        'Journal the bounded pre-release call on scheduled macro days - graded vs realized SPY/QQQ close',
        'job', '15 12 * * *', true, null, 20)
on conflict (name) do update set cron=excluded.cron, purpose=excluded.purpose,
       priority=excluded.priority;
