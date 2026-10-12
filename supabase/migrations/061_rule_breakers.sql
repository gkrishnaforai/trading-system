-- 061: Rule Breakers — milestone-ladder tracking for emerging/confirmed
-- high-conviction growers. Members carry the qualitative thesis
-- (checklist JSONB)— snapshots carry the quantitative proof each
-- evaluation run (rev growth, streak, margins, market cap).
CREATE TABLE IF NOT EXISTS rule_breaker_members (
    symbol TEXT PRIMARY KEY,
    tier TEXT NOT NULL DEFAULT 'watchlist',   -- watchlist|emerging|confirmed
    checklist JSONB NOT NULL DEFAULT '{}',     -- tam, moat, ai_exposure,
                                             -- vectors, optionality (bools)
                                             -- + ai_rev_pct, thesis (notes)
    promoted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rule_breaker_snapshots (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL REFERENCES rule_breaker_members(symbol)
        ON DELETE CASCADE,
    as_of DATE NOT NULL,
    rev_growth DOUBLE PRECISION,
    eps_growth DOUBLE PRECISION,
    rev_streak INT,
    eps_streak INT,
    gross_margin DOUBLE PRECISION,
    gross_margin_prev DOUBLE PRECISION,
    op_margin DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    price DOUBLE PRECISION,
    gates_met INT NOT NULL DEFAULT 0,
    gates_detail JSONB NOT NULL DEFAULT '{}',
    suggested_tier TEXT,
    UNIQUE (symbol, as_of)
);

CREATE INDEX IF NOT EXISTS idx_rb_snap_sym ON rule_breaker_snapshots (symbol, as_of DESC);
