-- 251_outlook_scores.sql — Phase D part 2: composite outlook journal.
--
-- ADMIN-ONLY output: the composite blends health trajectory, cohort
-- position, insider flow and filing-narrative tone — a heuristic
-- research signal, not a recommendation. admin_only stays true;
-- public release is A+B+E only per the frozen boundary.
--
-- The outcome journal is the grading columns — realized returns fill
-- later so the score's actual hit-rate is auditable, not asserted.

CREATE TABLE IF NOT EXISTS outlook_scores (
  id                 bigserial PRIMARY KEY,
  symbol             text NOT NULL,
  as_of              date NOT NULL,
  score              numeric,          -- 0-100 composite
  grade              text,             -- A|B|C|D|F bands
  components         jsonb,            -- {health_delta, cohort_relative,
                                       --  insider_flow, guidance_tone}
  inputs             jsonb,            -- lineage refs for audit
  score_version      text,
  admin_only         boolean DEFAULT true,
  realized_30d       numeric,
  realized_90d       numeric,
  realized_180d      numeric,
  graded_at          timestamptz,
  created_at         timestamptz DEFAULT now(),
  UNIQUE (symbol, as_of, score_version)
);
CREATE INDEX IF NOT EXISTS outlook_scores_sym_idx
  ON outlook_scores (symbol, as_of DESC);

INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('outlook-score',
        'Composite outlook scores (admin)',
        'D spine — health trajectory + cohort + insider + narrative '
        'tone → heuristic outlook; admin-only, outcome-graded',
        'job', '45 2 * * 0', true, 59)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
                                 enabled = EXCLUDED.enabled;
