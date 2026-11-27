-- 239_queue_groom.sql — queue hygiene as a first-class parent job.
--
-- Was: a step inside the custodian's ~10min pass. The custodian moved
-- out of the project (temp-custodian/ — standalone support-agent
-- work); queue hygiene stays because it is parent self-maintenance,
-- not supervision: pending events older than the TTL are cancelled
-- (dead work, honest status) and terminal rows are pruned in bounded
-- batches. Every 15 min keeps pending depth bounded without riding
-- the */5 dispatcher hot path.

INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('queue-groom',
        'Event-queue TTL + prune',
        'Pending universal_events older than 24h -> cancelled; '
        'terminal rows older than 7d pruned in bounded batches',
        'job', '*/15 * * * *', true, 80)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
    enabled = true, updated_at = NOW();

-- the in-worker custodian is gone from the codebase — if a catalog
-- row lingers from an earlier seed, retire it so the dispatcher
-- never fires a name with no handler
UPDATE job_definitions SET enabled = false, updated_at = NOW()
 WHERE name = 'custodian';
