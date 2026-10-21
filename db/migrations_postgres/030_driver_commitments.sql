-- 030 — driver commitments: the company's own stated growth engines
-- and forward numeric commitments, extracted verbatim from filings.
--
-- thesis_watches stays the single journal (each commitment also lands
-- there as driver:{metric}:{period}); this table carries the numeric
-- payload + the compare chain so a guide RAISE/CUT is arithmetic on
-- successive commitments, not prose.
--
-- status: open (awaiting the period's print) | superseded (a newer
--         commitment for the same metric+period replaced it —
--         check_note records the delta direction) | confirmed |
--         refuted | expired.

CREATE TABLE IF NOT EXISTS driver_commitments (
    id          BIGSERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL,
    metric      TEXT NOT NULL,            -- 'ad_revenue' | 'op_margin' | 'fcf' …
    period      TEXT NOT NULL,            -- 'FY26' | 'Q4-26' | '2027' …
    value       DOUBLE PRECISION,         -- 2.7e9  (normalized, raw units)
    value_text  TEXT,                     -- '~$2.7B' as stated
    direction   TEXT,                     -- 'at_least'|'approx'|'at_most'|'growth'
    prior_value DOUBLE PRECISION,         -- same metric+period, prior commitment
    delta_dir   TEXT,                     -- raised | cut | reaffirmed | new
    delta_pct   DOUBLE PRECISION,         -- (value-prior)/prior — negative = cut
    quote       TEXT,                     -- verbatim grounding (required)
    source      TEXT,                     -- '8-K 2026-10-20' / doc url
    status      TEXT NOT NULL DEFAULT 'open',
    check_note  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    checked_at  TIMESTAMPTZ,
    UNIQUE (symbol, metric, period, quote)
);

CREATE INDEX IF NOT EXISTS idx_driver_commitments_open
    ON driver_commitments (symbol, metric, period) WHERE status='open';
