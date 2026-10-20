-- 024: correction-alarm evals
-- Daily journal of the four-leg correction read. The
-- valuation_decomp leg needs this journal to accumulate before the
-- de-rating/earnings-cut split activates.

CREATE TABLE IF NOT EXISTS correction_evals (
    id                      BIGSERIAL PRIMARY KEY,
    as_of                   DATE NOT NULL DEFAULT CURRENT_DATE,
    correction_character    TEXT NOT NULL,
    severity                TEXT NOT NULL,
    readings                JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of)
);

CREATE INDEX IF NOT EXISTS idx_ce_asof ON correction_evals (as_of DESC);
