-- 246_fact_observations.sql — raw XBRL fact-observation layer.
--
-- Every XBRL fact the issuer ever reported is preserved EXACTLY as
-- received — value, period, precision fields are never normalized or
-- overwritten in place. Restatements and amendments arrive as new
-- observations keyed to their own accession; the resolver (not the
-- table) decides which observation is "currently preferred" or
-- "known as of" a point in time. That's what makes historical
-- backtests honest: the raw record never moves under you.
--
-- v1 scope: consolidated companyfacts only — the SEC companyfacts
-- API carries no dimensional/segment breakdown, so `dimensions`
-- stays NULL until the filing-instance iXBRL parser lands.

CREATE TABLE IF NOT EXISTS fact_observations (
  id              bigserial PRIMARY KEY,
  cik             text        NOT NULL,       -- issuer identity
  entity_cik      text,                       -- reserved: subsidiary/other-entity facts
  accn            text        NOT NULL,       -- accession that reported this fact
  taxonomy        text        NOT NULL,       -- 'us-gaap'|'dei'|'ifrs-full'|...
  tag             text        NOT NULL,       -- 'Revenues','NetCashProvidedByUsedIn...'
  unit            text        NOT NULL,       -- 'USD','shares','pure','USD/shares'
  value           numeric,                    -- raw value exactly as received
  decimals        integer,                    -- reported precision (NULL via companyfacts)
  period_start    date,                       -- duration facts; NULL for instants
  period_end      date        NOT NULL,
  instant         boolean     NOT NULL DEFAULT false,
  fy              integer,                    -- fiscal-year label as reported
  fp              text,                       -- 'Q1'..'Q4','FY','Q1I','H2',...
  frame           text,                       -- 'CY2024Q1' etc where SEC supplies it
  form            text,                       -- form that carried the fact
  filed_at        timestamptz,                -- companyfacts 'filed' — observation vintage
  is_amendment    boolean     NOT NULL DEFAULT false,
  is_derived      boolean     NOT NULL DEFAULT false,  -- true = our computation, not reported
  derived_from    jsonb,                      -- {source_fact_ids, rule} when is_derived
  dimensions      jsonb,                      -- NULL v1 — companyfacts is consolidated-only
  quality_state   text        NOT NULL DEFAULT 'reported'
                  CHECK (quality_state IN
                    ('reported','derived','missing','ambiguous',
                     'restated','rejected')),
  source_url      text,
  parser_version  text        NOT NULL DEFAULT 'a2_v1',
  source_fact_id  text        NOT NULL UNIQUE,  -- sha1 dedup: cik|accn|tax|tag|unit|start|end|val
  ingested_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS fact_obs_cik_tag_end_idx
  ON fact_observations (cik, tag, period_end DESC);
CREATE INDEX IF NOT EXISTS fact_obs_accn_idx
  ON fact_observations (accn);
CREATE INDEX IF NOT EXISTS fact_obs_filed_idx
  ON fact_observations (cik, tag, filed_at DESC);

-- companyfacts backfill — weekend/off-hours only (user directive:
-- historical loads run nights and weekends). ET cron; chunked +
-- resumable via edgar_ingest_state.facts_pulled_at.
INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('edgar-facts-backfill',
        'EDGAR companyfacts backfill',
        'XBRL fact-observation layer — companyfacts → fact_observations'
        ' for the tracked universe; chunked, resumable, off-hours',
        'job', '*/20 0-4,23 * * 0,6', true, 65)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
    enabled = true, updated_at = NOW();
