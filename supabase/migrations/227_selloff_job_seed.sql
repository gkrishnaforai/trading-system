-- selloff job: registered but unscheduled (cron NULL, enabled false).
-- Give it a nightly slot after flywheel (22:00 UTC) and the growth
-- jobs — its SBD overlay reads the flywheel aggregates +
-- growth_compare_daily revisions. Only fills where no schedule
-- exists; never overrides an existing one.
UPDATE job_definitions
   SET cron = '50 22 * * 1-5',
       enabled = true,
       timezone = 'UTC',
       dep_max_age_h = 24
 WHERE name = 'selloff' AND cron IS NULL;

UPDATE job_definitions
   SET depends_on = '{flywheel}'
 WHERE name = 'selloff' AND depends_on IS NULL;
