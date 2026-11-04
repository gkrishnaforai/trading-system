-- universe_snapshot: one row per symbol — the shared base-data
-- layer every rule job reads from (compute once, consume many).
-- Rollup of journaled tables; refresh is chunked (stale-first) so
-- a timeout resumes rather than restarts.
CREATE TABLE IF NOT EXISTS universe_snapshot (
    symbol              TEXT PRIMARY KEY,
    spot                DOUBLE PRECISION,
    spot_date           DATE,
    eps_ttm             DOUBLE PRECISION,
    fwd_eps             DOUBLE PRECISION,
    fy0_eps             DOUBLE PRECISION,
    fy2_eps             DOUBLE PRECISION,
    est_revision_pct    DOUBLE PRECISION,
    num_analysts        INTEGER,
    rev_growth          DOUBLE PRECISION,
    fcf_ttm             DOUBLE PRECISION,
    market_cap          DOUBLE PRECISION,
    momentum_state      TEXT,
    fv_expected         DOUBLE PRECISION,
    fv_upside_pct       DOUBLE PRECISION,
    lifecycle_stage     INTEGER,
    category            TEXT,
    backlog_yoy         DOUBLE PRECISION,
    book_to_bill        DOUBLE PRECISION,
    snapshot_as_of      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS universe_snapshot_stale
    ON universe_snapshot (snapshot_as_of);
