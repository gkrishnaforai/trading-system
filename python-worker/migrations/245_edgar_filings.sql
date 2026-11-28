-- 245_edgar_filings.sql — EDGAR filing event log + ingest cursor.
--
-- The identity layer of the public-data spine: every filing event a
-- tracked issuer posts to EDGAR lands here, keyed by accession number
-- (the immutable filing identity — ticker changes never touch it).
-- Amendments (10-Q/A, 8-K/A) are SEPARATE ROWS linked back via
-- amends_accession_number — never overwrites, because a restatement
-- is itself an event worth alerting on.
--
-- Everything downstream (fact observations, health scores, alerts)
-- keys off accession_number so each output can cite its filing.

CREATE TABLE IF NOT EXISTS edgar_filings (
  cik                      text        NOT NULL,  -- zero-padded 10-digit issuer CIK (stable identity)
  accession_number         text        NOT NULL PRIMARY KEY,  -- 0000320193-24-000123
  form                     text        NOT NULL,  -- '10-Q','10-Q/A','8-K','4',...
  filing_date              date        NOT NULL,
  acceptance_datetime      timestamptz,           -- SEC acceptance — true event sequencing
  report_period            date,                  -- period of report (submissions reportDate)
  primary_document         text,
  items                    text,                  -- 8-K item list ('2.02,9.01'); nullable, form-specific
  is_amendment             boolean     NOT NULL DEFAULT false,
  amends_accession_number  text,                  -- resolved: same base form + report_period, earlier acceptance
  document_url             text,
  content_hash             text,                  -- sha1 of primary doc once fetched (nullable till then)
  source_api               text        NOT NULL DEFAULT 'submissions',
  parser_version           text        NOT NULL DEFAULT 'a1_v1',
  ingested_at              timestamptz NOT NULL DEFAULT now(),
  UNIQUE (cik, accession_number)
);

CREATE INDEX IF NOT EXISTS edgar_filings_cik_form_idx
  ON edgar_filings (cik, form, filing_date DESC);
CREATE INDEX IF NOT EXISTS edgar_filings_period_idx
  ON edgar_filings (cik, report_period);
CREATE INDEX IF NOT EXISTS edgar_filings_symbol_cover_idx
  ON edgar_filings (filing_date DESC);

-- resumable ingest cursor — one row per tracked issuer. Backfill jobs
-- chunk the universe and resume from the cursor after any restart.
CREATE TABLE IF NOT EXISTS edgar_ingest_state (
  symbol              text PRIMARY KEY,
  cik                 text        NOT NULL,
  filings_scanned_at  timestamptz,            -- last submissions poll
  facts_pulled_at     timestamptz,            -- last companyfacts pull
  backfill_done       boolean     NOT NULL DEFAULT false,
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- nightly incremental scan + weekend-deep pass. ET cron (registry
-- convention); all stored timestamps stay UTC.
INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('edgar-filings-scan',
        'EDGAR filing-event scan',
        'Submissions index → edgar_filings event log; detects new '
        '10-Q/10-K/8-K and amendments for the tracked universe',
        'job', '0 1 * * *', true, 55)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
    enabled = true, updated_at = NOW();
