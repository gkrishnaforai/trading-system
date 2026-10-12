-- 060: analyst action tape — individual upgrades/downgrades/PT changes.
-- Captures event-level analyst moves ("Exane raised NBIS to $399 from
-- Neutral") rather than aggregate consensus drift. Fingerprint-deduped.
CREATE TABLE IF NOT EXISTS analyst_actions (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    kind TEXT NOT NULL,                 -- 'grade' | 'pt'
    firm TEXT,
    analyst_name TEXT,
    action TEXT,                        -- upgrade/downgrade/initiated/hold/raise/lower
    prev_grade TEXT,
    new_grade TEXT,
    price_target DOUBLE PRECISION,
    price_when_posted DOUBLE PRECISION,
    title TEXT,
    url TEXT,
    fingerprint TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analyst_actions_sym_time
    ON analyst_actions (symbol, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyst_actions_time
    ON analyst_actions (published_at DESC);
