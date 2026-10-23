-- 151_lev_etf_evals.sql — journal for the 3x-semiconductor swing
-- detector (leveraged_swings.py). One row per (as_of, etf): the state
-- machine verdict (flat/armed/triggered/vetoed), the full checklist,
-- and the computed entry/stop/target geometry — so the backtest can
-- grade whether the setups actually pay after costs, which is the
-- only question a 3x product ever answers.

-- python-worker AND go-api both apply this tree at boot — serialize
-- concurrent appliers (see 150_best_picks.sql).
SELECT pg_advisory_xact_lock(715151);

CREATE TABLE IF NOT EXISTS lev_etf_evals (
    id            BIGSERIAL PRIMARY KEY,
    as_of         DATE         NOT NULL,
    etf           TEXT         NOT NULL,   -- SOXS | SOXL
    signal_src    TEXT         NOT NULL,   -- SMH (index proxy)
    state         TEXT         NOT NULL,   -- flat|armed|triggered|vetoed
    rsi           NUMERIC(5,1),            -- index RSI14
    vs50          NUMERIC(7,4),            -- index close/50dma - 1
    ema8_rel      NUMERIC(7,4),            -- index close/EMA8 - 1
    idx_close     NUMERIC(12,2),
    etf_px        NUMERIC(12,2),
    stop_px       NUMERIC(12,2),           -- ETF-level invalidation
    t1_px         NUMERIC(12,2),           -- 1.5R partial
    t2_px         NUMERIC(12,2),           -- 2R partial
    risk_pct_px   NUMERIC(7,4),            -- |entry-stop|/entry
    checklist     JSONB,                   -- [{ok, line}] every leg
    veto          TEXT,                    -- veto reason when vetoed
    leaders       JSONB,                   -- leader tape snapshot
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (as_of, etf)
);

CREATE INDEX IF NOT EXISTS lev_etf_evals_asof_idx
    ON lev_etf_evals (as_of DESC, etf);

-- scheduled after the momentum refresh so the index tape is today's
INSERT INTO job_definitions (name, label, cron, enabled)
VALUES ('lev-etf-swings', '3x semis swing detector', '45 22 * * *', true)
ON CONFLICT (name) DO NOTHING;
