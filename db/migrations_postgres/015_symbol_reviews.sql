-- Event-review journal — every deep review (event-triggered or
-- weekly) journaled so each verdict is gradable later. Answers to the
-- five standing questions stored as structured evidence, not prose.
CREATE TABLE IF NOT EXISTS symbol_reviews (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL,
    as_of       TIMESTAMPTZ NOT NULL DEFAULT now(),
    trigger     TEXT NOT NULL,        -- weekly | alert:<kind> | sec:<kind> | manual
    verdict     TEXT NOT NULL,        -- accumulate | hold | trim | wait | insufficient
    score       NUMERIC,              -- evidence balance (-x .. +x)
    answers     JSONB NOT NULL,       -- {q1..q5: {lines[], facts{}}}
    reasons     JSONB,                -- verdict driver lines
    run_id      TEXT
);
CREATE INDEX IF NOT EXISTS symbol_reviews_sym
    ON symbol_reviews(symbol, as_of DESC);

INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('weekly-review', 'Weekly 5-question review', '0 10 * * 0', true)
ON CONFLICT (name) DO NOTHING;

-- doc_extract's journal — referenced by doc_extract.analyze and the
-- new sec-filings path; was never provisioned on this deployment.
CREATE TABLE IF NOT EXISTS doc_analyses (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL,
    url         TEXT,
    title       TEXT,
    thesis      TEXT,
    claims      JSONB,
    dropped     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS doc_analyses_sym
    ON doc_analyses(symbol, created_at DESC);
