-- job seeds for the demand-evidence feed + AI-cycle ladder.
-- The evidence feed ran zero times before (its only trigger was the
-- admin API), which is why market_ai_regime graded all-unknown.
-- Ladder runs after ingest so the evidence leg sees fresh claims.
-- NB: the migration runner splits statements on ';' — no semicolons
-- inside string literals.

INSERT INTO job_definitions (name, label, purpose, cron, enabled,
                             depends_on, dep_max_age_h, cooldown_min,
                             priority)
VALUES
  ('demand-evidence', 'Demand-evidence feed (capex/FCF + news drafts)',
   'Deterministic capex + FCF claims per ingest group auto-approved, '
   'news extraction lands as drafts. Feeds market_ai_regime + the '
   'cycle ladder evidence leg',
   '10 22 * * 1-5', true, NULL, 30, 30, 55),
  ('ai-cycle-ladder', 'AI cycle theme ladder (daily)',
   'Per-stage rungs (build/deploy/utilize) with tape + growth + '
   'evidence + funding legs journaled to ai_cycle_ladder_daily. '
   'rotation_state keeps evidence_led vs tape_led honest',
   '40 22 * * 1-5', true, '{demand-evidence}', 30, 5, 45)
ON CONFLICT (name) DO UPDATE SET
  label = EXCLUDED.label,
  purpose = EXCLUDED.purpose,
  cron = EXCLUDED.cron,
  enabled = EXCLUDED.enabled,
  depends_on = EXCLUDED.depends_on,
  dep_max_age_h = EXCLUDED.dep_max_age_h,
  priority = EXCLUDED.priority;
