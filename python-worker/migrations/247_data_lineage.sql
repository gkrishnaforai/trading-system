-- 247_data_lineage.sql — provenance graph + materialized eligibility.
--
-- The public-eligibility gate: every derived output (metric, score,
-- alert, narrative) records its inputs as edges here. Recursive
-- leaves are classified public vs licensed via the SOURCE_LICENSE
-- map; the result is materialized into output_eligibility at write
-- time (fast API reads) while a separate audit re-walks the graph to
-- prove it. If an upstream fact is restated or a source reclassified,
-- downstream eligibility rows are recomputed — a cached TRUE can
-- never outlive the inputs it was computed on.

CREATE TABLE IF NOT EXISTS data_lineage (
  id                     bigserial PRIMARY KEY,
  output_type            text NOT NULL,   -- 'fact','metric','score','alert','narrative','filing','statement_row'
  output_id              text NOT NULL,   -- stable id of the output record
  input_type             text NOT NULL,
  input_id               text NOT NULL,
  data_source            text NOT NULL,   -- 'sec_edgar'|'fmp'|'yahoo'|...
  license_class          text NOT NULL DEFAULT 'licensed'
                         CHECK (license_class IN ('public','licensed')),
  transformation_version text,
  created_at             timestamptz NOT NULL DEFAULT now(),
  UNIQUE (output_type, output_id, input_type, input_id)
);

CREATE INDEX IF NOT EXISTS data_lineage_output_idx
  ON data_lineage (output_type, output_id);
CREATE INDEX IF NOT EXISTS data_lineage_input_idx
  ON data_lineage (input_type, input_id);

-- materialized eligibility — computed at write, verified by audit
CREATE TABLE IF NOT EXISTS output_eligibility (
  output_type               text        NOT NULL,
  output_id                 text        NOT NULL,
  public_eligible           boolean     NOT NULL,
  lineage_complete          boolean     NOT NULL,
  public_leaf_count         integer     NOT NULL DEFAULT 0,
  restricted_leaf_count     integer     NOT NULL DEFAULT 0,
  lineage_hash              text,                    -- sha1 over sorted leaf set — drift detector
  eligibility_checked_at    timestamptz NOT NULL DEFAULT now(),
  eligibility_policy_version text       NOT NULL DEFAULT '1.0',
  PRIMARY KEY (output_type, output_id)
);

CREATE INDEX IF NOT EXISTS output_eligibility_public_idx
  ON output_eligibility (output_type, public_eligible);

-- resolver pass — runs after facts land; incremental thereafter.
INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('edgar-resolve',
        'EDGAR facts → canonical statements',
        'Resolve fact_observations → 8q quarterly statements '
        '(sec_edgar source) + lineage edges + public eligibility',
        'job', '*/20 0-4,23 * * 0,6', true, 66)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
    enabled = true, updated_at = NOW();
