-- 249_filing_narratives.sql — Phase C of the public-data spine.
--
-- LLM extraction over 10-Q/10-K MD&A + Risk Factors (EDGAR text only).
-- Every claim is verbatim-quote grounded, journaled per filing, and
-- carries provenance rows the lineage layer can audit:
--
--   filing_narratives   per-filing extraction journal (accession-keyed)
--   claim_evidence      claim → filing/section/quote provenance
--   claim_metric_links  claim → structured metric linkage

CREATE TABLE IF NOT EXISTS filing_narratives (
  accession_number   text PRIMARY KEY,
  symbol             text NOT NULL,
  cik                text,
  form               text,
  report_period      date,
  filing_date        date,
  sections_found     jsonb,          -- {mda: chars, risk_factors: chars}
  claims_emitted     integer,
  claims_dropped     integer,
  llm_model          text,
  parser_version     text,
  status             text,           -- done | no_sections | no_doc | error
  extracted_at       timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS filing_narratives_sym_idx
  ON filing_narratives (symbol, filing_date DESC);

CREATE TABLE IF NOT EXISTS claim_evidence (
  id                 bigserial PRIMARY KEY,
  claim_id           text NOT NULL,
  accession_number   text NOT NULL,
  symbol             text,
  section            text,           -- mda | risk_factors
  quote              text,           -- verbatim grounded span
  source_url         text,
  filed_at           date,
  parser_version     text,
  created_at         timestamptz DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS claim_evidence_uidx
  ON claim_evidence (claim_id, accession_number, md5(quote));
CREATE INDEX IF NOT EXISTS claim_evidence_claim_idx
  ON claim_evidence (claim_id);
CREATE INDEX IF NOT EXISTS claim_evidence_accn_idx
  ON claim_evidence (accession_number);

CREATE TABLE IF NOT EXISTS claim_metric_links (
  id                 bigserial PRIMARY KEY,
  claim_id           text NOT NULL,
  symbol             text,
  metric             text,
  value              numeric,
  prior_value        numeric,
  period             text,
  direction          text,
  created_at         timestamptz DEFAULT now(),
  UNIQUE (claim_id, metric, period)
);
CREATE INDEX IF NOT EXISTS claim_metric_links_claim_idx
  ON claim_metric_links (claim_id);

INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('filing-narrative',
        '10-Q/10-K sections → grounded claims',
        'C spine — MD&A + Risk Factors → verbatim-grounded claims, '
        'evidence rows, metric links, lineage edges (2x/wk)',
        'job', '45 1 * * 2,5', true, 66)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
                                 enabled = EXCLUDED.enabled;
