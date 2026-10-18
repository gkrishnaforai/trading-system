-- SEC EDGAR fundamentals + flywheel FCF/M&A columns.
--
-- symbol_sec_facts: structured facts pulled from SEC XBRL
-- companyfacts — the fields FMP doesn't carry (backlog/RPO, goodwill,
-- acquisition cash, share-count history). The share-count series is
-- also the authoritative split detector: a >1.8x step in
-- CommonStockSharesOutstanding means every per-share series that
-- straddles the date is on a mixed basis (NOW Dec-2025 5:1).
CREATE TABLE IF NOT EXISTS symbol_sec_facts (
    symbol          TEXT PRIMARY KEY,
    cik             TEXT,
    rpo             NUMERIC,          -- remaining performance obligation (backlog)
    crpo            NUMERIC,          -- current RPO (due within 12m) when disclosed
    rpo_period      TEXT,             -- fiscal period the RPO fact covers
    goodwill        NUMERIC,
    goodwill_assets_pct NUMERIC,      -- goodwill / total assets
    acq_spend_fy    NUMERIC,          -- cash paid for acquisitions, latest FY
    shares_out      NUMERIC,          -- latest CommonStockSharesOutstanding
    shares_step_ratio NUMERIC,        -- largest consecutive step in share count
    split_suspect   BOOLEAN NOT NULL DEFAULT FALSE,
    facts           JSONB,            -- raw extracted facts + share series + notes
    as_of           DATE,             -- latest fact end date
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- dedupe 8-K → doc_extract so each earnings release is analyzed once
CREATE TABLE IF NOT EXISTS sec_filings_processed (
    accession       TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    form            TEXT NOT NULL,
    filed           DATE,
    url             TEXT,
    claims          INT,              -- valid claims journaled
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS sec_filings_processed_sym
    ON sec_filings_processed(symbol, filed DESC);

-- flywheel: FCF + acquisition-spend legs (filled by the expectation-gap
-- job from the cash-flow quarters it already fetches)
ALTER TABLE symbol_flywheel
    ADD COLUMN IF NOT EXISTS fcf_ttm NUMERIC,
    ADD COLUMN IF NOT EXISTS fcf_margin NUMERIC,
    ADD COLUMN IF NOT EXISTS fcf_growth NUMERIC,
    ADD COLUMN IF NOT EXISTS acq_spend_ttm NUMERIC,
    ADD COLUMN IF NOT EXISTS acq_rev_pct NUMERIC;

-- default schedules — sync_registry's ON CONFLICT only rewrites the
-- label, so these crons survive the code-side resync. sec-facts is
-- weekly (XBRL facts change only on filings); sec-filings runs
-- weeknights after close so same-day releases land overnight.
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('sec-facts',   'SEC XBRL fundamentals',            '0 9 * * 6',   true),
       ('sec-filings', '8-K earnings-release extraction',  '30 21 * * 1-5', true)
ON CONFLICT (name) DO NOTHING;
