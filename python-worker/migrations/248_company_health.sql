-- 248_company_health.sql — quarterly company-health journal.
--
-- The product layer over the EDGAR spine: one row per (symbol,
-- period) per scoring pass — versioned, never overwritten (a
-- restatement-driven rescore marks the old row superseded, so the
-- "what did we know then" record survives).
--
-- Score semantics per the frozen spec: overall score publishes ONLY
-- when coverage >= 60% AND all critical legs resolve (balance-sheet,
-- cash-flow, earnings-quality). Missing data is never a clean score
-- — below the gate the row carries verdict='insufficient_data' with
-- category scores still populated.

CREATE TABLE IF NOT EXISTS company_health_quarterly (
  id                bigserial PRIMARY KEY,
  symbol            text        NOT NULL,
  cik               text,
  period_end        date        NOT NULL,
  score             integer,                     -- NULL when insufficient_data
  verdict           text        NOT NULL DEFAULT 'insufficient_data'
                    CHECK (verdict IN ('scored','insufficient_data')),
  coverage_pct      numeric,                     -- resolved-leg weight / total
  confidence        text        CHECK (confidence IN ('high','medium','low')),
  available_legs    jsonb,
  missing_legs      jsonb,
  category_scores   jsonb,                       -- {cat:{score,weight,evidence}}
  drivers           jsonb,                       -- [{metric,direction,contribution,evidence_accn}]
  red_flags         jsonb,                       -- [{class,pattern,values,evidence_accn}]
  ewf_state         text,                        -- GREEN|YELLOW|RED early-warning state
  quality_score     integer,                     -- earnings_quality composite
  trend             text,                        -- improving|stable|deteriorating|new
  previous_score    integer,
  score_delta       integer,
  filing_accn       text,                        -- accession this quarter cites
  score_version     text        NOT NULL DEFAULT 'b1_v1',
  superseded        boolean     NOT NULL DEFAULT false,
  computed_at       timestamptz NOT NULL DEFAULT now()
);

-- one live row per symbol+period; history lives in superseded rows
CREATE UNIQUE INDEX IF NOT EXISTS company_health_live_uidx
  ON company_health_quarterly (symbol, period_end)
  WHERE NOT superseded;
CREATE INDEX IF NOT EXISTS company_health_sym_idx
  ON company_health_quarterly (symbol, period_end DESC);

-- health scoring — runs post-resolve, off-hours; incremental on
-- new-statement events going forward
INSERT INTO job_definitions (name, label, purpose, kind, cron,
                             enabled, priority)
VALUES ('company-health',
        'Quarterly company health scores',
        'EDGAR-derived quarterly health: coverage-gated score, '
        'category legs, structured drivers, 4-class alert emission',
        'job', '*/30 0-5,22-23 * * *', true, 67)
ON CONFLICT (name) DO UPDATE SET cron = EXCLUDED.cron,
    enabled = true, updated_at = NOW();
