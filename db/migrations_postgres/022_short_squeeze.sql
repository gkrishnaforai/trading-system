-- 022: short-squeeze evaluations
-- Daily snapshot of squeeze_fuel / covering_probability per symbol so
-- the learning loop can later answer "do covering-flagged rallies
-- fade?" and "do squeeze_setups actually rip?".

CREATE TABLE IF NOT EXISTS short_squeeze_evals (
    id                      BIGSERIAL PRIMARY KEY,
    symbol                  TEXT NOT NULL,
    as_of                   DATE NOT NULL DEFAULT CURRENT_DATE,
    fuel                    NUMERIC(5,1),
    covering_probability    NUMERIC(5,1),
    verdict                 TEXT NOT NULL,
    data_quality            TEXT,
    rally                   BOOLEAN,
    ret_5d                  NUMERIC(8,4),
    rel_vol                 NUMERIC(8,2),
    si_pct                  NUMERIC(8,2),
    days_to_cover           NUMERIC(8,2),
    sv_ratio_latest         NUMERIC(8,2),
    sv_trend                NUMERIC(8,2),
    evidence                JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_sse_asof ON short_squeeze_evals (as_of DESC);
CREATE INDEX IF NOT EXISTS idx_sse_verdict ON short_squeeze_evals (verdict, as_of DESC);
