-- Priority ordering + enable the daily cadence.
-- Lower priority fires first when multiple jobs are due the same
-- minute— depends_on still gates correctness (a job waits for a clean
-- predecessor run regardless of priority).
ALTER TABLE job_definitions
    ADD COLUMN IF NOT EXISTS priority int NOT NULL DEFAULT 50;

UPDATE job_definitions SET priority = CASE name
    WHEN 'custodian'     THEN 5    -- watchdog cadence (own loop anyway)
    WHEN 'regime'        THEN 10   -- posture first: gates aggression
    WHEN 'alerts'        THEN 15   -- inbox early, feeds reviews
    WHEN 'focus-scan'    THEN 16
    WHEN 'momentum'      THEN 20   -- tape flags: the base layer
    WHEN 'leaps-mark'    THEN 25   -- mark book on fresh tape
    WHEN 'flywheel'      THEN 30   -- fundamentals
    WHEN 'fund-flags'    THEN 35   -- needs flywheel fresh (dep too)
    WHEN 'rule-breakers' THEN 40
    WHEN 'smallcap'      THEN 41
    WHEN 'swing-scan'    THEN 50   -- needs momentum (dep)
    WHEN 'outcomes'      THEN 60   -- grading tail
    WHEN 'pilot'         THEN 70   -- after flags settle
    WHEN 'priors'        THEN 80   -- heavy replay — weekly
    WHEN 'all'           THEN 90   -- box job, manual default
    ELSE 50 END;

-- Enable the daily set. 'all' stays manual (the big red button)—
-- 'custodian' stays on its dedicated loop (a watchdog must not depend
-- on the scheduler it watches).
UPDATE job_definitions SET enabled = true, updated_at = now()
WHERE name IN ('regime','momentum','flywheel','fund-flags','alerts',
               'focus-scan','swing-scan','rule-breakers','smallcap',
               'outcomes','leaps-mark','priors','pilot');
