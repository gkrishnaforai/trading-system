-- 112_ingestion_jobs.sql — repair the dead data-ingestion paths.
--
-- Diagnosis (Oct 2026): the Go-side `weekly_fundamentals_enhanced`
-- schedule stopped ticking in Feb and its profile name never resolved
-- in the Go job map. `financial_growth` / `income_statement_growth` /
-- `*_growth` data types exist in python but are in NO Go profile, and
-- `macro_market_data` had no scheduled writer at all (last row Jan 6).
-- Result: the fair-value engine correctly refused stale inputs — but
-- the upstream pipeline was silently dead.
--
-- Fix: two python-side board jobs (same job_runs ledger the rest of
-- the system uses):
--   macro-snapshot   — daily: MacroRefreshService → macro_market_data
--   fund-snapshots   — weekly Sat: per-symbol refresh of fundamentals,
--                      key_metrics_ttm, financial_growth, growth
--                      statements, ratios, scores via refresh_manager

INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES
  ('macro-snapshot', 'Macro market snapshot',
   'Daily VIX/TNX/IRX/Nasdaq-trend row → macro_market_data '
   '(feeds FV WACC/discount features)',
   '5 12 * * 1-5', true, NULL, 24, 5, 15),
  ('fund-snapshots', 'Fundamental snapshots',
   'Weekly refresh of fmp_fundamentals/key_metrics/financial_growth/'
   'growth-statements/ratios/scores → stock_insights_snapshots '
   '(the fair-value engine inputs)',
   '20 14 * * 6', true, NULL, 168, 5, 20)
ON CONFLICT (name) DO NOTHING;
