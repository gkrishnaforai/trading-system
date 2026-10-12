-- Per-symbol ranks per run — normalized history of sector/theme candidate
-- rankings. sector_candidate_runs holds the JSONB blob— this table makes
-- rank movement queryable (who's climbing/falling between runs).

CREATE TABLE IF NOT EXISTS candidate_ranks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      uuid NOT NULL REFERENCES sector_candidate_runs(id) ON DELETE CASCADE,
    basket      text NOT NULL,            -- 'XLK' or 'agentic_ai'
    basket_kind text NOT NULL,            -- sector | theme
    symbol      text NOT NULL,
    rank        integer,
    score       numeric,                  -- rank_score or theme_score
    fund_score  numeric,
    tier        integer,                  -- theme purity tier (NULL for sectors)
    verdict     text,
    eps_growth  numeric,
    rev_growth  numeric,
    roe         numeric,
    rd_intensity numeric,
    price       numeric,
    dd20_pct    numeric
);

CREATE INDEX IF NOT EXISTS idx_candidate_ranks_run
    ON candidate_ranks (run_id);
CREATE INDEX IF NOT EXISTS idx_candidate_ranks_basket_run
    ON candidate_ranks (basket, run_id);
