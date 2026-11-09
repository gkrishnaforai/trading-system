-- sec-filings (8-K earnings extraction) was registered but never
-- scheduled — guidance data only lands where claims were extracted.
-- Run it post-close weeknights, BEFORE guidance (22:30) so fresh
-- claims feed the same night's scores.
SELECT pg_advisory_xact_lock(715192);

UPDATE job_definitions SET
    cron = '0 22 * * 1-5',
    enabled = true,
    priority = 15
 WHERE name = 'sec-filings' AND (cron IS NULL OR cron = '');

-- guidance consumes the claims — declare the dependency
UPDATE job_definitions SET
    depends_on = ARRAY['sec-filings'],
    dep_max_age_h = 30
 WHERE name = 'guidance';
