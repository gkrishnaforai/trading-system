-- 109_doc_analysis.sql — curated-document extraction.
-- User-pasted articles/notes get a bounded LLM pass (fixed question
-- set, quote-grounded) → channel claims journal into `tailwinds`,
-- falsifiable watch items land in `thesis_watches` for grading when
-- fundamentals refresh, and every run is audited in `doc_analyses`.
-- The LLM extracts claims only — no scores, no targets, no recs.

CREATE TABLE IF NOT EXISTS doc_analyses (
    id          bigserial PRIMARY KEY,
    symbol      text NOT NULL,
    url         text,
    title       text,
    thesis      text,
    claims      jsonb,                  -- validated claims
    dropped     jsonb,                  -- claims killed by validation
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS thesis_watches (
    id          bigserial PRIMARY KEY,
    symbol      text NOT NULL,
    metric      text NOT NULL,          -- 'optical segment revenue'
    threshold   text,                   -- '>5% of revenue'
    horizon     text,                   -- 'FY28' / '2027-Q1'
    direction   text DEFAULT 'confirm', -- confirm | refute
    source      text,                   -- doc url/title
    status      text DEFAULT 'open',    -- open | confirmed | refuted | stale
    check_note  text,
    created_at  timestamptz DEFAULT now(),
    checked_at  timestamptz,
    UNIQUE (symbol, metric, horizon)
);
