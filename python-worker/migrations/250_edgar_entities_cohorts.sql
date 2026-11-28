-- 250_edgar_entities_cohorts.sql — Phase D part 1: issuer identity
-- + cohort snapshots.
--
-- edgar_entities: one row per issuer (cik-keyed) carrying SIC identity
-- — the submissions payload's entity fields, journaled by the filings
-- scan. SIC is the cohort key: ticker-stable and issuer-assigned.
--
-- cohort_snapshots: "public-filing-based cohort intelligence" —
-- aggregate + median + quartile metrics per SIC cohort per snapshot
-- date. Always labeled; survivorship warning is structural (the
-- cohort is the tracked universe, not the full industry).

CREATE TABLE IF NOT EXISTS edgar_entities (
  cik                text PRIMARY KEY,
  symbol             text,
  entity_name        text,
  sic                text,
  sic_description    text,
  fy_end             text,
  entity_type        text,
  updated_at         timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS edgar_entities_sic_idx
  ON edgar_entities (sic);

CREATE TABLE IF NOT EXISTS cohort_snapshots (
  id                 bigserial PRIMARY KEY,
  cohort_key         text NOT NULL,        -- 'sic:NN' (2-digit division)
  cohort_label       text,
  as_of              date NOT NULL,
  member_count       integer,
  reporting_coverage_pct numeric,
  fiscal_period_alignment jsonb,           -- {period_end: member count}
  metrics            jsonb,                -- {metric: {aggregate, median,
                                          --          p25, p75, n}}
  composition_version text,
  survivorship_bias_warning boolean DEFAULT true,
  label              text
        DEFAULT 'public-filing-based cohort intelligence',
  created_at         timestamptz DEFAULT now(),
  UNIQUE (cohort_key, as_of, composition_version)
);

INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('cohort-snapshot',
        'SIC cohort snapshots',
        'D spine — aggregate+median cohort metrics from EDGAR health '
        'rows; labeled public-filing-based, survivorship-flagged',
        'job', '30 2 * * 0', true, 60)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
                                 enabled = EXCLUDED.enabled;
